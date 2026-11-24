"""Data pipeline without network: Apify item shapes, anonymization, extraction, set ids and
prices, with fake Apify and TCGdex clients."""

import json

from src.config import ROOT
from src.pipeline import (
    MarketplaceScraper,
    PriceBook,
    TCGdex,
    anon_id,
    anonymize,
    apply_scope_filter,
    build_listings,
    extract_cards,
    resolve_set,
    run_ingest,
)

RAW = json.loads((ROOT / "data/samples/sample_raw_listings.json").read_text(encoding="utf-8"))
SETS = [
    {"id": "base1", "name": "Base Set"},
    {"id": "base4", "name": "Base Set 2"},
    {"id": "sv03.5", "name": "151"},
    {"id": "swsh4", "name": "Vivid Voltage"},
]


def test_anonymize_drops_seller_and_keeps_description_text():
    row = anonymize(RAW[1])
    assert row["listing_id"] == anon_id(RAW[1]["id"]) and row["listing_id"].startswith("fb_")
    assert row["raw_description"].startswith("Zelle only")  # text, not "{'text': ...}"
    assert row["delivery_type"] == "shipping"
    assert "seller" not in json.dumps(row).lower()
    assert anonymize({**RAW[0], "listing_price": {"amount": "0"}}) is None  # no $0 listings
    assert anonymize({**RAW[0], "is_sold": True}) is None


def test_extract_build_and_scope_filter(llm):
    rows = [r for r in (anonymize(i) for i in RAW) if r]
    listings = build_listings(rows, extract_cards(llm, rows, batch_size=10, log=None))
    kept, dropped = apply_scope_filter(listings)
    assert dropped["graded"] >= 1 and dropped["is_lot"] >= 1 and dropped["non_english"] >= 1
    zard = next(x for x in kept if x.raw_title.startswith("Charizard base set 4/102"))
    assert (zard.card_name, zard.set_name, zard.number, zard.condition) == (
        "Charizard", "Base Set", "4", "LP"
    )  # fmt: skip
    assert zard.price == 320.0  # the model can never change the price


def test_resolve_set_prefers_exact_names_and_accepts_ids():
    assert resolve_set("Base Set", SETS) == "base1"  # not Base Set 2
    assert resolve_set("Scarlet & Violet—151", SETS) == "sv03.5"
    assert resolve_set("base1", SETS) == "base1"
    assert resolve_set("Nonexistent Set", SETS) is None


class FakeTCGdex(TCGdex):
    def __init__(self):
        self.asked = []

    def sets(self):
        return SETS

    def card(self, set_id, number):
        self.asked.append(f"{set_id}-{number}")
        if set_id == "base1" and number == "4":
            return {
                "name": "Charizard",
                "set": {"name": "Base Set"},
                "pricing": {"tcgplayer": {"unit": "USD", "holofoil": {"marketPrice": 400.0}}},
            }
        return None


class FakeRun:
    default_dataset_id = "ds1"  # apify-client 3.x returns an object, not a dict


class FakeApify:
    def __init__(self, items):
        self.items, self.run_input = items, None

    def actor(self, _name):
        return self

    def call(self, run_input, max_total_charge_usd):
        self.run_input, self.cap = run_input, max_total_charge_usd
        return FakeRun()

    def dataset(self, _id):
        return self

    def iterate_items(self):
        return iter(self.items)


def test_scraper_sends_actor_input_and_reads_run_object(cfg, tmp_path):
    cfg["data"]["raw_dir"] = str(tmp_path)
    fake = FakeApify(RAW[:3])
    items = MarketplaceScraper(cfg, client=fake).search(["pokemon charizard"], 5, 0.5)
    assert len(items) == 3 and list(tmp_path.glob("snapshot_*.json"))
    assert fake.run_input["startUrls"][0]["url"].startswith("https://www.facebook.com/marketplace/")
    assert fake.run_input["resultsLimit"] == 5 and float(fake.cap) == 0.5


def test_run_ingest_writes_listings_prices_and_review_sheet(cfg, llm, tmp_path):
    for key, name in [("prices", "prices.json"), ("tcgdex_sets", "sets.json"),
                      ("review_sheet", "review.csv")]:  # fmt: skip
        cfg["data"][key] = str(tmp_path / name)
    book = PriceBook(cfg, {}, client=FakeTCGdex())
    out = tmp_path / "listings.json"
    summary = run_ingest(cfg, llm, RAW, pricebook=book, out_path=out, log=lambda *_: None)
    assert summary["kept"] > 0 and out.exists() and (tmp_path / "review.csv").exists()
    assert book.prices["base1-4"]["variants"] == {"holofoil": 400.0}
    assert "base1-4" in json.loads((tmp_path / "prices.json").read_text())


def test_load_data_uses_samples(data):
    assert data.source == "samples" and len(data.listings) == 24
    assert "base1-4" in data.prices and data.red_flags
