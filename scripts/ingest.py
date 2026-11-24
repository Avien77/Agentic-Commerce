"""Day 1 Data Pipeline: Apify snapshot -> anonymize -> LLM card extraction -> scope filter -> TCGdex prices.

Usage:
  uv run python scripts/ingest.py --mode test          # 5-listing Apify test run
  uv run python scripts/ingest.py --mode full          # 50-100 listing snapshot
  uv run python scripts/ingest.py --skip-scrape        # Re-run extraction/prices on existing data/raw/snapshot.json
"""

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import diskcache
import httpx
from dotenv import load_dotenv

from src.config import load_config
from src.schemas import CardListing

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "snapshot.json"
LISTINGS_PATH = ROOT / "data" / "listings.json"
PRICES_PATH = ROOT / "data" / "prices.json"
CACHE_DIR = ROOT / ".cache" / "ingest"

TCGDEX_URL = "https://api.tcgdex.net/v2/en/cards/{set_code}-{number}"


def parse_price(raw_price: Any) -> float:
    if isinstance(raw_price, (int, float)):
        return float(raw_price)
    if isinstance(raw_price, str):
        match = re.search(r"[\d,]+(?:\.\d{1,2})?", raw_price)
        if match:
            return float(match.group(0).replace(",", ""))
    return 0.0


def scrape_apify(queries: list[str], max_items: int) -> list[dict[str, Any]]:
    """Run Apify Facebook Marketplace Scraper and save raw snapshot (gitignored)."""
    from apify_client import ApifyClient

    token = os.getenv("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError("APIFY_API_TOKEN missing in .env")

    client = ApifyClient(token)
    all_items: list[dict[str, Any]] = []
    per_query = max(1, max_items // max(1, len(queries)))

    for q in queries:
        run_input = {
            "searchQuery": q,
            "maxItems": per_query,
        }
        # Apify official Facebook Marketplace Scraper actor
        run = client.actor("apify/facebook-marketplace-scraper").call(run_input=run_input)
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        all_items.extend(items)

    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_PATH, "w", encoding="utf-8") as f:
        json.dump(all_items, f, indent=2)
    print(f"Saved {len(all_items)} raw listings to {RAW_PATH}")
    return all_items


def anonymize_raw_item(raw: dict[str, Any], idx: int) -> dict[str, Any]:
    """Section 14: Drop seller name, seller ID, and listing URL; keep city-level location."""
    title = str(raw.get("marketplace_listing_title") or raw.get("title") or "").strip()
    description = str(raw.get("redacted_description") or raw.get("description") or "").strip()
    price = parse_price(
        raw.get("listing_price", {}).get("amount")
        if isinstance(raw.get("listing_price"), dict)
        else raw.get("price", 0)
    )
    location = raw.get("location") or {}
    city = (
        location.get("reverse_geocode", {}).get("city", "")
        if isinstance(location, dict)
        else str(location)
    )
    delivery_raw = str(raw.get("delivery_types") or raw.get("delivery_type") or "").lower()
    if "pickup" in delivery_raw or "in_person" in delivery_raw or "local" in delivery_raw:
        delivery_type = "in_person"
    elif "shipping" in delivery_raw:
        delivery_type = "shipping"
    else:
        delivery_type = "unknown"

    has_photo = bool(raw.get("primary_listing_photo") or raw.get("photo") or raw.get("images"))

    return {
        "listing_id": f"fb_{idx:04d}",
        "raw_title": title,
        "raw_description": description,
        "price": price,
        "location_city": city,
        "delivery_type": delivery_type,
        "has_clear_photo": has_photo,
    }


def extract_card_fields_llm(
    item: dict[str, Any],
    model_id: str,
    cache: diskcache.Cache,
) -> CardListing:
    """Use Gemini structured output (cached on disk) to extract exact card identity."""
    from google import genai

    prompt = (
        "Extract structured Pokemon TCG card fields from this marketplace listing. "
        "Use TCGdex set codes (e.g. 'base1', 'swsh1', 'sv01'). "
        "If unsure about a field, use 'unknown' and lower confidence (<0.7). "
        "Never assume shipping is 0 unless explicitly stated.\n\n"
        f"Title: {item['raw_title']}\n"
        f"Description: {item['raw_description']}\n"
        f"Price: {item['price']}\n"
        f"Delivery type: {item['delivery_type']}"
    )
    cache_key = f"{model_id}:{hashlib.sha256(prompt.encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return CardListing(**{**item, **cached})

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": CardListing,
            "temperature": 0.0,
        },
    )
    extracted = json.loads(response.text)
    # Preserve anonymized base fields so LLM cannot overwrite price/ID
    merged = {**extracted, **item}
    cache.set(cache_key, extracted)
    return CardListing(**merged)


def apply_scope_filter(listings: list[CardListing]) -> tuple[list[CardListing], dict[str, int]]:
    """Section 4 Step 3: Drop graded cards, lots/binders, and non-English printings."""
    kept: list[CardListing] = []
    dropped = {"graded": 0, "is_lot": 0, "non_english": 0}

    for card in listings:
        if card.graded:
            dropped["graded"] += 1
            continue
        if card.is_lot:
            dropped["is_lot"] += 1
            continue
        if card.language.lower() != "en":
            dropped["non_english"] += 1
            continue
        kept.append(card)

    return kept, dropped


def fetch_tcgdex_prices(listings: list[CardListing]) -> dict[str, Any]:
    """Section 4 Step 4: Cache TCGdex market prices to data/prices.json."""
    prices: dict[str, Any] = {}
    if PRICES_PATH.exists():
        with open(PRICES_PATH, "r", encoding="utf-8") as f:
            prices = json.load(f)

    unique_keys = {
        f"{c.set_code}-{c.number}"
        for c in listings
        if c.set_code != "unknown" and c.number != "unknown"
    }

    with httpx.Client(timeout=15.0) as client:
        for card_key in sorted(unique_keys):
            if card_key in prices:
                continue
            set_code, number = card_key.split("-", 1)
            url = TCGDEX_URL.format(set_code=set_code, number=number)
            try:
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    tcgplayer = data.get("pricing", {}).get("tcgplayer", {})
                    prices[card_key] = {
                        "name": data.get("name"),
                        "tcgplayer": tcgplayer,
                    }
                else:
                    prices[card_key] = {"error": f"HTTP {resp.status_code}", "tcgplayer": {}}
            except httpx.HTTPError as exc:
                prices[card_key] = {"error": str(exc), "tcgplayer": {}}

    PRICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PRICES_PATH, "w", encoding="utf-8") as f:
        json.dump(prices, f, indent=2)
    print(f"Cached {len(prices)} card price entries to {PRICES_PATH}")
    return prices


def main() -> None:
    load_dotenv()
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Day 1 ingestion pipeline")
    parser.add_argument("--mode", choices=["test", "full"], default="test")
    parser.add_argument("--skip-scrape", action="store_true")
    parser.add_argument("--skip-prices", action="store_true")
    parser.add_argument(
        "--queries",
        nargs="+",
        default=["pokemon charizard", "pokemon card pikachu"],
    )
    args = parser.parse_args()

    if args.skip_scrape:
        if not RAW_PATH.exists():
            raise FileNotFoundError(f"No raw snapshot found at {RAW_PATH}")
        with open(RAW_PATH, "r", encoding="utf-8") as f:
            raw_items = json.load(f)
    else:
        max_items = 5 if args.mode == "test" else 100
        raw_items = scrape_apify(args.queries, max_items=max_items)

    anonymized = [anonymize_raw_item(item, i) for i, item in enumerate(raw_items)]

    model_id = cfg["models"]["primary"]
    cache = diskcache.Cache(str(CACHE_DIR))
    extracted = [extract_card_fields_llm(item, model_id, cache) for item in anonymized]

    kept, dropped = apply_scope_filter(extracted)
    low_conf = [
        c.listing_id
        for c in kept
        if c.confidence < cfg["thresholds"]["extraction_confidence_review"]
    ]

    LISTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LISTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump([c.model_dump() for c in kept], f, indent=2)

    print(f"Extracted: {len(extracted)} | Kept: {len(kept)} | Dropped: {dropped}")
    print(f"Rows needing manual review (confidence < 0.7): {len(low_conf)} -> {low_conf}")

    if not args.skip_prices:
        fetch_tcgdex_prices(kept)


if __name__ == "__main__":
    main()
