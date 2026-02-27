import json
import requests
from groq import Groq
from Bio import Entrez
from app.config import settings
from app.db import fetchone, execute


if settings.ENTREZ_EMAIL:
    Entrez.email = settings.ENTREZ_EMAIL


client = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None


def ensure_products_schema():
    execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            product_name TEXT PRIMARY KEY,
            brand TEXT,
            sugar_g NUMERIC,
            ingredients TEXT,
            usda_signal TEXT,
            review_signals JSONB,
            pubmed_findings JSONB,
            final_insight TEXT,
            data_source TEXT DEFAULT 'pipeline',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )


def get_cached_insight(product_name: str):
    row = fetchone(
        "SELECT final_insight FROM products WHERE product_name = %s LIMIT 1",
        (product_name,),
    )
    return row[0] if row and row[0] else None


def save_insight(product_name, brand, sugar_g, ingredients, usda_signal, review_signals, pubmed_findings, final_insight):
    execute(
        """
        INSERT INTO products (
            product_name, brand, sugar_g, ingredients, usda_signal, review_signals, pubmed_findings, final_insight, data_source
        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        ON CONFLICT (product_name) DO UPDATE
        SET brand = EXCLUDED.brand,
            sugar_g = EXCLUDED.sugar_g,
            ingredients = EXCLUDED.ingredients,
            usda_signal = EXCLUDED.usda_signal,
            review_signals = EXCLUDED.review_signals,
            pubmed_findings = EXCLUDED.pubmed_findings,
            final_insight = EXCLUDED.final_insight,
            data_source = EXCLUDED.data_source,
            updated_at = NOW()
        """,
        (
            product_name,
            brand,
            sugar_g,
            ingredients,
            usda_signal,
            json.dumps(review_signals),
            json.dumps(pubmed_findings),
            final_insight,
            "pipeline",
        ),
    )


def fetch_openfoodfacts(product_name):
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {
        "search_terms": product_name,
        "search_simple": 1,
        "action": "process",
        "json": 1,
    }
    data = requests.get(url, params=params, timeout=20).json()
    if data.get("count", 0) == 0:
        return None

    product = data["products"][0]
    return {
        "name": product.get("product_name", "Unknown"),
        "brand": product.get("brands", "Unknown"),
        "sugar": float(product.get("nutriments", {}).get("sugars_100g", 0) or 0),
        "ingredients": product.get("ingredients_text", "No ingredients listed"),
        "categories": product.get("categories_tags", []),
    }


def fetch_pubmed_abstracts(ingredients, max_items=3):
    if not settings.ENTREZ_EMAIL:
        return [{"warning": "ENTREZ_EMAIL not set"}]

    findings = []
    for ingredient in ingredients[:max_items]:
        try:
            term = f"{ingredient} health effects"
            handle = Entrez.esearch(db="pubmed", term=term, retmax=1)
            record = Entrez.read(handle)
            handle.close()

            ids = record.get("IdList", [])
            if not ids:
                findings.append({"ingredient": ingredient, "summary": "No PubMed result found"})
                continue

            handle = Entrez.efetch(db="pubmed", id=ids[0], rettype="abstract", retmode="text")
            abstract = handle.read()
            handle.close()
            findings.append({"ingredient": ingredient, "summary": abstract[:500]})
        except Exception as exc:
            findings.append({"ingredient": ingredient, "summary": f"PubMed error: {exc}"})

    return findings


def fetch_review_signals(product_name):
    if not settings.SERPAPI_KEY:
        return ["SERPAPI_KEY not set"]

    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google",
        "q": f"{product_name} reviews",
        "num": 10,
        "api_key": settings.SERPAPI_KEY,
    }
    data = requests.get(url, params=params, timeout=20).json()

    snippets = []
    for item in data.get("organic_results", []):
        text = " ".join([item.get("title", ""), item.get("snippet", "")]).strip()
        if text:
            snippets.append(text)

    keywords = ["misleading", "hidden", "formula change", "aftertaste", "artificial", "too sweet"]
    matches = []
    for s in snippets:
        lower = s.lower()
        hit = [k for k in keywords if k in lower]
        if hit:
            matches.append({"text": s[:220], "keywords": hit})

    if not snippets:
        return ["No review snippets returned by SerpApi"]
    if not matches:
        return ["No discrepancy keywords found in top review snippets"]
    return matches[:5]


def _extract_nutrient(food, name):
    for nutrient in food.get("foodNutrients", []):
        nutrient_name = (nutrient.get("nutrientName") or "").lower()
        if name in nutrient_name:
            value = nutrient.get("value")
            if value is not None:
                return float(value)
    return None


def _to_sugar_per_100g(food):
    sugar = _extract_nutrient(food, "sugars")
    if sugar is None:
        return None

    serving_size = food.get("servingSize")
    serving_unit = (food.get("servingSizeUnit") or "").lower()

    if serving_size and serving_unit == "g" and serving_size > 0:
        return sugar * 100.0 / float(serving_size)

    return sugar


def get_usda_percentile_signal(product_name, target_sugar_100g):
    if not settings.USDA_API_KEY:
        return "USDA_API_KEY not set"

    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    payload = {
        "query": product_name,
        "pageSize": 50,
        "dataType": ["Branded", "Survey (FNDDS)"],
    }
    data = requests.post(url, params={"api_key": settings.USDA_API_KEY}, json=payload, timeout=20).json()

    sugar_values = []
    for food in data.get("foods", []):
        sugar_100g = _to_sugar_per_100g(food)
        if sugar_100g is not None:
            sugar_values.append(sugar_100g)

    if not sugar_values:
        return "USDA returned no comparable sugar values"

    sugar_values.sort()
    n = len(sugar_values)
    leq = sum(1 for x in sugar_values if x <= target_sugar_100g)
    percentile = round((leq / n) * 100, 1)
    avg = round(sum(sugar_values) / n, 2)

    return (
        f"USDA benchmark: sugar {target_sugar_100g} g/100g is around the {percentile}th percentile "
        f"across {n} similar USDA items (mean={avg} g/100g)."
    )


def build_final_insight(product_name, food_data, pubmed_findings, review_signals, usda_signal):
    if not client:
        return (
            f"{product_name} ({food_data['brand']}) has {food_data['sugar']} g sugar per 100g. "
            f"USDA signal: {usda_signal}. "
            f"Review/PubMed notes collected but LLM summary unavailable because GROQ_API_KEY is missing."
        )

    prompt = f"""
You are a food scientist assistant. Write exactly 3 concise sentences.
Product: {product_name}
Brand: {food_data['brand']}
Sugar (per 100g): {food_data['sugar']}
Ingredients: {food_data['ingredients']}
USDA signal: {usda_signal}
Review signals: {review_signals}
PubMed findings: {pubmed_findings}
"""

    completion = client.chat.completions.create(
        model=settings.MODEL_NAME,
        messages=[
            {"role": "system", "content": "You produce grounded, concise nutrition risk summaries."},
            {"role": "user", "content": prompt},
        ],
    )
    return completion.choices[0].message.content


def run_pipeline(product_name: str) -> dict:
    ensure_products_schema()

    cached = get_cached_insight(product_name)
    if cached:
        return {"source": "postgres_cache", "insight": cached}

    food_data = fetch_openfoodfacts(product_name)
    if not food_data:
        return {"source": "pipeline", "insight": "Product not found in Open Food Facts."}

    ingredients = [i.strip() for i in food_data["ingredients"].split(",") if i.strip()]
    pubmed_findings = fetch_pubmed_abstracts(ingredients, max_items=3)
    review_signals = fetch_review_signals(product_name)
    usda_signal = get_usda_percentile_signal(product_name, food_data["sugar"])

    final_insight = build_final_insight(
        product_name=product_name,
        food_data=food_data,
        pubmed_findings=pubmed_findings,
        review_signals=review_signals,
        usda_signal=usda_signal,
    )

    save_insight(
        product_name=product_name,
        brand=food_data["brand"],
        sugar_g=food_data["sugar"],
        ingredients=food_data["ingredients"],
        usda_signal=usda_signal,
        review_signals=review_signals,
        pubmed_findings=pubmed_findings,
        final_insight=final_insight,
    )

    return {"source": "pipeline", "insight": final_insight}
