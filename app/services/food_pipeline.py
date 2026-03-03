import json
import re
import requests
from groq import Groq
from Bio import Entrez
from app.config import settings
from app.db import fetchone, execute


if settings.ENTREZ_EMAIL:
    Entrez.email = settings.ENTREZ_EMAIL


client = Groq(api_key=settings.GROQ_API_KEY) if settings.GROQ_API_KEY else None


QUESTION_FILLER = {
    "is",
    "are",
    "was",
    "were",
    "can",
    "could",
    "should",
    "would",
    "do",
    "does",
    "did",
    "the",
    "a",
    "an",
    "for",
    "about",
    "please",
    "tell",
    "me",
    "analyze",
    "check",
    "product",
    "food",
    "item",
    "healthy",
    "healthier",
    "good",
    "bad",
    "insights",
    "insight",
    "review",
    "reviews",
}


def _clean_text(value: str) -> str:
    return " ".join(value.strip().split())


def _fallback_extract_product_name(user_query: str) -> str:
    text = re.sub(r"[^A-Za-z0-9\s\-']", " ", user_query)
    text = _clean_text(text)
    if not text:
        return "Unknown product"

    # Try to keep the phrase after common anchors.
    for anchor in ("about ", "for ", "of "):
        idx = text.lower().find(anchor)
        if idx >= 0 and idx + len(anchor) < len(text):
            candidate = _clean_text(text[idx + len(anchor):])
            if candidate:
                text = candidate
                break

    tokens = [t for t in text.split() if t.lower() not in QUESTION_FILLER]
    if tokens:
        return " ".join(tokens[:8])
    return text


def detect_product_name(user_query: str) -> str:
    if not user_query.strip():
        return "Unknown product"

    if not client:
        return _fallback_extract_product_name(user_query)

    prompt = (
        "Extract the food/product name from the user text. "
        "Return only the product name with no extra words. "
        "If unclear, return UNKNOWN.\n\n"
        f"User text: {user_query}"
    )
    try:
        completion = client.chat.completions.create(
            model=settings.MODEL_NAME,
            messages=[
                {"role": "system", "content": "You extract product names from user questions."},
                {"role": "user", "content": prompt},
            ],
        )
        extracted = _clean_text(completion.choices[0].message.content or "")
        if not extracted or extracted.upper() == "UNKNOWN":
            return _fallback_extract_product_name(user_query)
        return extracted
    except Exception:
        return _fallback_extract_product_name(user_query)


def ensure_products_schema():
    execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            product_name TEXT PRIMARY KEY,
            brand TEXT,
            sugar_g NUMERIC,
            fat_g NUMERIC,
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
    execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS fat_g NUMERIC")


def get_cached_product(product_name: str):
    row = fetchone(
        """
        SELECT product_name, brand, sugar_g, fat_g, ingredients, usda_signal, review_signals, pubmed_findings, final_insight
        FROM products
        WHERE LOWER(product_name) = LOWER(%s) OR LOWER(product_name) LIKE LOWER(%s)
        ORDER BY CASE WHEN LOWER(product_name) = LOWER(%s) THEN 0 ELSE 1 END, updated_at DESC
        LIMIT 1
        """,
        (product_name, f"%{product_name}%", product_name),
    )
    if not row:
        return None

    return {
        "product_name": row[0],
        "brand": row[1],
        "sugar": float(row[2]) if row[2] is not None else None,
        "fat": float(row[3]) if row[3] is not None else None,
        "ingredients": row[4] or "No ingredients listed",
        "usda_signal": row[5] or "USDA signal unavailable",
        "review_signals": row[6] if row[6] is not None else [],
        "pubmed_findings": row[7] if row[7] is not None else [],
        "final_insight": row[8] or "",
    }


def save_insight(product_name, brand, sugar_g, fat_g, ingredients, usda_signal, review_signals, pubmed_findings, final_insight):
    execute(
        """
        INSERT INTO products (
            product_name, brand, sugar_g, fat_g, ingredients, usda_signal, review_signals, pubmed_findings, final_insight, data_source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
        ON CONFLICT (product_name) DO UPDATE
        SET brand = EXCLUDED.brand,
            sugar_g = EXCLUDED.sugar_g,
            fat_g = EXCLUDED.fat_g,
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
            fat_g,
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
    data = None
    for timeout_s in (8, 16):
        try:
            resp = requests.get(url, params=params, timeout=timeout_s)
            resp.raise_for_status()
            data = resp.json()
            break
        except requests.RequestException:
            continue

    if not data:
        return None

    if data.get("count", 0) == 0:
        return None

    product = data["products"][0]
    return {
        "name": product.get("product_name", "Unknown"),
        "brand": product.get("brands", "Unknown"),
        "sugar": float(product.get("nutriments", {}).get("sugars_100g", 0) or 0),
        "fat": float(product.get("nutriments", {}).get("fat_100g", 0) or 0),
        "ingredients": product.get("ingredients_text", "No ingredients listed"),
        "categories": product.get("categories_tags", []),
    }


def _clip(text, max_len=180):
    out = _clean_text(str(text or ""))
    if len(out) <= max_len:
        return out
    return out[: max_len - 3] + "..."


def _as_list(value):
    if isinstance(value, list):
        return value
    return []


def _top_review_signal(review_signals):
    signals = _as_list(review_signals)
    if not signals:
        return "According to user reviews, the taste is generally acceptable with no strong negative trend."

    first = signals[0]
    if isinstance(first, dict):
        keywords = first.get("keywords") or []
        text = first.get("text") or ""
        if keywords:
            return f"According to user reviews, common feedback includes: {', '.join(keywords[:3])}."
        if text:
            return f"According to user reviews, {_clip(text, 120)}"
    return f"According to user reviews, {_clip(first, 120)}"


def _top_pubmed_signal(pubmed_findings):
    findings = _as_list(pubmed_findings)
    if not findings:
        return "According to scientific evidence, there is no clear PubMed signal available yet."

    first = findings[0]
    if isinstance(first, dict):
        ingredient = first.get("ingredient") or "ingredient"
        summary = first.get("summary") or "No PubMed summary."
        return f"According to scientific evidence, {ingredient} is associated with: {_clip(summary, 110)}"
    return f"According to scientific evidence, {_clip(first, 120)}"


def _format_num(value):
    if value is None:
        return "0"
    return str(round(float(value), 2)).rstrip("0").rstrip(".")


def _scientific_summary(product_name, usda_signal, pubmed_findings):
    usda = _clean_text(str(usda_signal or ""))
    match = re.search(r"sugar\s+([0-9.]+)\s+g/100g.*?around the\s+([0-9.]+)th percentile.*?across\s+(\d+)", usda, re.IGNORECASE)
    if match:
        sugar = str(round(float(match.group(1)), 1)).rstrip("0").rstrip(".")
        percentile_value = float(match.group(2))
        if percentile_value >= 75:
            advice = (
                f"According to scientific evidence, {product_name} is fine occasionally but has a high glucose/sugar load, "
                "so avoid taking it on an empty stomach and keep portions small."
            )
        elif percentile_value >= 40:
            advice = (
                f"According to scientific evidence, {product_name} is generally okay in moderation, "
                "and it is better after a meal than on an empty stomach."
            )
        else:
            advice = (
                f"According to scientific evidence, {product_name} has a relatively supportive sugar profile "
                "and can fit regular intake in balanced portions."
            )
        return advice

    findings = _as_list(pubmed_findings)
    for item in findings:
        if not isinstance(item, dict):
            continue
        summary = _clean_text(str(item.get("summary") or ""))
        if (
            not summary
            or "no pubmed result found" in summary.lower()
            or summary.lower().startswith("pubmed error:")
        ):
            continue
        ingredient = _clean_text(str(item.get("ingredient") or ""))
        if ingredient:
            return f"According to scientific evidence, {product_name} may offer nutritional benefits from {ingredient}, and it is best taken in moderate portions."
        return f"According to scientific evidence, {product_name} can be included in a balanced diet with mindful portions."

    return None


def _review_five_words(review_signals):
    signals = _as_list(review_signals)
    if not signals:
        return None

    first = signals[0]
    if isinstance(first, dict):
        keywords = first.get("keywords") or []
        if keywords:
            phrase = " ".join(str(k) for k in keywords[:2])
        else:
            phrase = _clean_text(str(first.get("text") or ""))
    else:
        phrase = _clean_text(str(first))
        blocked = (
            "serpapi_key not set",
            "no review snippets returned by serpapi",
            "no discrepancy keywords found in top review snippets",
        )
        if phrase.lower() in blocked:
            return None

    words = phrase.replace(",", " ").split()
    filtered = [w for w in words if w.lower() not in {"according", "to", "user", "reviews", "includes", "common", "feedback"}]
    if not filtered:
        return None
    final_words = filtered[:5]
    return " ".join(final_words).lower()


def _format_three_bullets(product_name, brand, sugar, fat, usda_signal, review_signals, pubmed_findings):
    sugar_text = _format_num(sugar)
    fat_text = "no fat" if fat is None or float(fat) <= 0 else f"{_format_num(fat)} g fat"
    bullets = [f"- {product_name} ({brand}) contains about {sugar_text} g sugar and {fat_text} per 100g."]

    science = _scientific_summary(product_name, usda_signal, pubmed_findings)
    if science:
        bullets.append(f"- {science}")

    review = _review_five_words(review_signals)
    if review:
        bullets.append(f"- Common feedback includes: {review}.")

    return "\n".join(bullets)


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
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return []

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
    try:
        resp = requests.post(url, params={"api_key": settings.USDA_API_KEY}, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return ""

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


def build_final_insight(product_name, food_data, pubmed_findings, review_signals, usda_signal, user_query):
    return _format_three_bullets(
        product_name=product_name,
        brand=food_data["brand"],
        sugar=food_data["sugar"],
        fat=food_data.get("fat"),
        usda_signal=usda_signal,
        review_signals=review_signals,
        pubmed_findings=pubmed_findings,
    )


def run_pipeline(user_query: str) -> dict:
    ensure_products_schema()
    product_name = detect_product_name(user_query)

    cached = get_cached_product(product_name)
    if cached:
        insight = _format_three_bullets(
            product_name=cached["product_name"],
            brand=cached["brand"],
            sugar=cached["sugar"],
            fat=cached["fat"],
            usda_signal=cached["usda_signal"],
            review_signals=cached["review_signals"],
            pubmed_findings=cached["pubmed_findings"],
        )
        return {
            "source": "postgres_cache",
            "product_name": cached["product_name"],
            "insight": insight,
        }

    food_data = fetch_openfoodfacts(product_name)
    if not food_data and product_name.lower() != user_query.lower():
        # Retry with original user text in case extraction was too aggressive.
        food_data = fetch_openfoodfacts(user_query)
        if food_data:
            product_name = food_data["name"]

    if not food_data:
        return {
            "source": "pipeline",
            "product_name": product_name,
            "insight": (
                "- I could not find this product in your database or Open Food Facts.\n"
                "- Try a more specific name with brand (example: 'Coca-Cola Zero 330ml').\n"
                "- Once found, I will summarize USDA, review, and PubMed signals in 3 points."
            ),
        }

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
        user_query=user_query,
    )

    save_insight(
        product_name=product_name,
        brand=food_data["brand"],
        sugar_g=food_data["sugar"],
        fat_g=food_data.get("fat"),
        ingredients=food_data["ingredients"],
        usda_signal=usda_signal,
        review_signals=review_signals,
        pubmed_findings=pubmed_findings,
        final_insight=final_insight,
    )

    return {"source": "pipeline", "product_name": product_name, "insight": final_insight}
