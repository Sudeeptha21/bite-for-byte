import os
import json
import requests
import psycopg2
from dotenv import load_dotenv
from groq import Groq
from Bio import Entrez

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DB_NAME = os.getenv("DB_NAME", "food_ai")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
ENTREZ_EMAIL = os.getenv("ENTREZ_EMAIL")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
USDA_API_KEY = os.getenv("USDA_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("Set GROQ_API_KEY in your environment or .env")
if not DB_PASSWORD:
    raise ValueError("Set DB_PASSWORD in your environment or .env")
if not ENTREZ_EMAIL:
    raise ValueError("Set ENTREZ_EMAIL in your environment or .env")

Entrez.email = ENTREZ_EMAIL
client = Groq(api_key=GROQ_API_KEY)

def get_conn():
    return psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )
def ensure_schema():
    stmts = [
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
        """,
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS brand TEXT",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS sugar_g NUMERIC",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS ingredients TEXT",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS usda_signal TEXT",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS review_signals JSONB",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS pubmed_findings JSONB",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS final_insight TEXT",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS data_source TEXT DEFAULT 'pipeline'",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW()",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW()",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_products_product_name ON products(product_name)",
    ]

    conn = get_conn()
    try:
        cur = conn.cursor()
        for stmt in stmts:
            cur.execute(stmt)
        conn.commit()
        cur.close()
    finally:
        conn.close()

def test_db_connection():
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT current_database(), current_user")
        row = cur.fetchone()
        cur.close()
        return row
    finally:
        conn.close()

def get_cached_insight(product_name):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT final_insight FROM products WHERE product_name = %s LIMIT 1", (product_name,))
        row = cur.fetchone()
        cur.close()
        if row and row[0]:
            return row[0]
        return None
    finally:
        conn.close()

def save_insight(product_name, brand, sugar_g, ingredients, usda_signal, review_signals, pubmed_findings, final_insight):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
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
        conn.commit()
        cur.close()
    finally:
        conn.close()
        
def fetch_openfoodfacts(product_name):
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {
        "search_terms": product_name,
        "search_simple": 1,
        "action": "process",
        "json": 1,
    }
    data = requests.get(url, params=params, timeout=60).json()
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
    findings = []
    for ingredient in ingredients[:max_items]:
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

    return findings

def fetch_review_signals(product_name):
    if not SERPAPI_KEY:
        return ["SERPAPI_KEY not set"]

    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google",
        "q": f"{product_name} reviews",
        "num": 10,
        "api_key": SERPAPI_KEY,
    }
    data = requests.get(url, params=params, timeout=60).json()

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
    if not USDA_API_KEY:
        return "USDA_API_KEY not set"

    url = "https://api.nal.usda.gov/fdc/v1/foods/search"
    payload = {
        "query": product_name,
        "pageSize": 50,
        "dataType": ["Branded", "Survey (FNDDS)"],
    }
    data = requests.post(url, params={"api_key": USDA_API_KEY}, json=payload, timeout=30).json()

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
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": "You produce grounded, concise nutrition risk summaries."},
            {"role": "user", "content": prompt},
        ],
    )
    return completion.choices[0].message.content

def run_pipeline(product_name):
    ensure_schema()
    db_name, db_user = test_db_connection()
    print(f"Connected to DB: {db_name} as {db_user}")

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

# Example run
result = run_pipeline("Chobani Blueberry Yogurt")
print(result["source"])
print(result["insight"])
