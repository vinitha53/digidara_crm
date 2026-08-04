import requests
from flask import current_app
from models import CompanySettings


def _match_name(customer_name, author_name):
    if not customer_name or not author_name:
        return False
    customer = " ".join(customer_name.lower().split())
    author = " ".join(author_name.lower().split())
    return customer == author or customer in author or author in customer


def find_customer_review(customer):
    settings = CompanySettings.query.get(1)
    place_id = current_app.config.get("GOOGLE_REVIEW_PLACE_ID") or (settings.google_review_place_id if settings else "")
    api_key = current_app.config.get("GOOGLE_REVIEW_API_KEY") or (settings.google_review_api_key if settings else "")
    if not place_id or not api_key:
        return {"ok": False, "skipped": True, "error": "Google Place ID and API key are required in Settings > Integrations."}

    params = {
        "place_id": place_id,
        "fields": "reviews,rating,user_ratings_total",
        "key": api_key,
    }
    try:
        response = requests.get("https://maps.googleapis.com/maps/api/place/details/json", params=params, timeout=15)
        data = response.json() if response.content else {}
    except requests.RequestException as exc:
        return {"ok": False, "error": str(exc)}

    if not response.ok or data.get("status") not in {"OK", "ZERO_RESULTS"}:
        return {"ok": False, "error": data.get("error_message") or data.get("status") or "Google review lookup failed."}

    result = data.get("result") or {}
    for review in result.get("reviews", []):
        if _match_name(customer.name, review.get("author_name")):
            return {
                "ok": True,
                "matched": True,
                "rating": int(review.get("rating")),
                "author_name": review.get("author_name"),
                "review_text": review.get("text"),
            }
    return {
        "ok": True,
        "matched": False,
        "place_rating": result.get("rating"),
        "user_ratings_total": result.get("user_ratings_total"),
    }
