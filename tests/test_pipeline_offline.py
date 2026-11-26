"""Data pipeline without network: Apify item shapes, anonymization, extraction, set ids and
prices, with fake Apify and TCGdex clients."""

import json
from typing import ClassVar

from src.config import ROOT
from src.pipeline import (
    IdentifiedCache,
    MarketplaceScraper,
    PriceBook,
    TCGdex,
    anon_id,
    anonymize,
    apply_scope_filter,
    build_listings,
    extract_cards,
    identify_listings,
    prefilter,
    resolve_set,
    review_reasons,
    run_ingest,
    scrape_snapshot,
    write_review_sheet,
)
from src.schemas import CardListing

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
    assert row["location_city"] == "Detroit, MI" and row["condition_label"] == "Used - like new"
    assert anonymize({**RAW[0], "listingPrice": {"amount": "0.00"}}) is None  # "make an offer"
    assert anonymize({**RAW[0], "isSold": True}) is None
    # the older snake_case field names still work
    old = {"id": "x", "marketplace_listing_title": "Mew", "listing_price": {"amount": "5"},
           "redacted_description": {"text": "mint"}, "delivery_types": ["SHIPPING"]}  # fmt: skip
    assert anonymize(old)["raw_description"] == "mint"


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


def test_snapshot_runs_each_search_and_keeps_listings_once(cfg, tmp_path):
    cfg["data"]["raw_dir"] = str(tmp_path)
    fake = FakeApify(RAW[:3])  # every search returns the same 3 listings
    items = scrape_snapshot(cfg, MarketplaceScraper(cfg, client=fake), per_query=3, log=None)
    assert len(items) == 3  # found by all 10 searches, kept once
    assert len(list(tmp_path.glob("snapshot_*.json"))) == 1  # one combined raw file
    assert float(fake.cap) == cfg["scrape"]["max_charge_usd"] / len(cfg["scrape"]["queries"])


# ---------------------------------------------------------------------------- real-data fixes
def test_anonymize_keeps_listing_signals_and_drops_placeholder_prices(cfg):
    item = {**RAW[0], "listingPhotos": [{}, {}, {}, {}], "timestamp": "2026-11-20T16:32:23.000Z",
            "location": {"latitude": 42.4895, "longitude": -83.1446},
            "deliveryTypes": ["IN_PERSON", "PUBLIC_MEETUP"], "isPending": True}  # fmt: skip
    row = anonymize(item, cfg)
    assert (row["photo_count"], row["listed_at"], row["public_meetup"], row["pending"]) == (
        4, "2026-11-20", True, True
    )  # fmt: skip
    assert 10 < row["distance_miles"] < 13  # Royal Oak is about 11 miles from Detroit
    assert "latitude" not in json.dumps(row)  # only the distance is kept
    one_dollar = {**RAW[0], "listingPrice": {"amount": "1.00"}}
    assert anonymize(one_dollar, cfg) is None  # "$1, make an offer"
    assert anonymize(one_dollar) is not None  # without a config only $0 is a placeholder


def test_set_aliases_and_printed_set_size(cfg, tmp_path):
    cfg["data"]["tcgdex_sets"] = str(tmp_path / "sets.json")
    sets = [{"id": "svp", "name": "SVP Black Star Promos"},
            {"id": "sv10", "name": "Destined Rivals", "cardCount": {"official": 182}},
            {"id": "sv04", "name": "Paradox Rift", "cardCount": {"official": 182}},
            {"id": "neo2", "name": "Neo Discovery", "cardCount": {"official": 75}},
            {"id": "A1", "name": "Genetic Apex", "cardCount": {"official": 75},
             "logo": "https://assets.tcgdex.net/en/tcgp/A1/logo"}]  # fmt: skip
    assert (
        resolve_set("Scarlet & Violet Black Star Promos", sets, cfg["tcgdex"]["set_aliases"])
        == "svp"
    )

    class Sets(FakeTCGdex):
        def sets(self):
            return sets

    book = PriceBook(cfg, {}, client=Sets())
    umbreon = CardListing(listing_id="u", raw_title="Umbreon 13/75 Neo Discovery", price=700,
                          card_name="Umbreon", set_name="Neo Genesis", number="13")  # fmt: skip
    mewtwo = CardListing(listing_id="m", raw_title="Team Rocket's Mewtwo ex 231/182", price=400,
                         card_name="Team Rocket's Mewtwo ex", number="231")  # fmt: skip
    book.resolve_sets([umbreon, mewtwo])
    assert umbreon.set_code == "neo2"  # only one real set has 75 cards (TCG Pocket ignored)
    assert mewtwo.set_code == "unknown"  # two sets have 182 cards: verify_cards decides


class GymTCGdex(FakeTCGdex):
    """gym2-14 is Rocket's Mewtwo; Sabrina's Gengar is gym1-14; nothing has M Gengar EX."""

    CARDS: ClassVar[dict[tuple[str, str], str]] = {
        ("gym1", "14"): "Sabrina's Gengar",
        ("gym2", "14"): "Rocket's Mewtwo",
        ("xy4", "56"): "Purrloin",
        ("sv10", "231"): "Team Rocket's Mewtwo ex",
    }

    def sets(self):
        return [{"id": i, "name": i, "cardCount": {"official": n}}
                for i, n in (("gym1", 132), ("gym2", 132), ("xy4", 119), ("sv04", 182),
                             ("sv10", 182))]  # fmt: skip

    def card(self, set_id, number):
        self.asked.append(f"{set_id}-{number}")
        name = self.CARDS.get((set_id, number))
        if not name:
            return None
        return {"name": name, "set": {"name": set_id},
                "pricing": {"tcgplayer": {"holofoil": {"marketPrice": 100.0}}}}  # fmt: skip


def test_verify_cards_fixes_the_set_or_drops_a_wrong_price(cfg, tmp_path):
    cfg["data"]["tcgdex_sets"] = str(tmp_path / "sets.json")
    book = PriceBook(cfg, {}, client=GymTCGdex())
    gengar = CardListing(listing_id="g", raw_title="Sabrina's Gengar 14/132 Gym Challenge",
                         price=750, card_name="Sabrina's Gengar", set_code="gym2", number="14",
                         confidence=0.95)  # fmt: skip
    mega = CardListing(listing_id="x", raw_title="Mega Gengar EX 056/119", price=5,
                       card_name="M Gengar EX", set_code="xy4", number="56", confidence=0.9)  # fmt: skip
    mewtwo = CardListing(listing_id="m", raw_title="Team Rocket's Mewtwo ex 231/182", price=400,
                         card_name="Team Rocket's Mewtwo ex", number="231", confidence=0.7)  # fmt: skip
    listings = [gengar, mega, mewtwo]
    book.resolve_sets(listings)
    book.ensure_prices(listings, pause_s=0)
    fixed, bad = book.verify_cards(listings)
    assert gengar.set_code == "gym1" and mewtwo.set_code == "sv10"  # the set with this card
    assert sorted(fixed) == ["g", "m"] and "gym1-14" in book.prices and "sv10-231" in book.prices
    assert bad == ["x"] and mega.set_code == "unknown" and mega.card_key is None
    assert mega.confidence == cfg["ingest"]["name_mismatch_confidence"]


def test_promo_cards_are_found_by_their_promo_number():
    t = TCGdex("https://tcgdex.test")
    pages = {
        "https://tcgdex.test/sets/xyp": {"cards": [{"id": "xyp-XY121", "localId": "XY121"}]},
        "https://tcgdex.test/cards/xyp-XY121": {"name": "Charizard EX"},
    }
    t._get = pages.get
    assert t.card("xyp", "121") == {"name": "Charizard EX"}
    assert t.card("xyp", "999") is None


def test_review_sheet_lists_why_a_row_needs_a_check(cfg, tmp_path):
    cfg["data"]["review_sheet"] = str(tmp_path / "review.csv")
    ok = CardListing(listing_id="a", raw_title="t", price=1, set_code="base1", number="4",
                     confidence=0.9)  # fmt: skip
    unpriced = CardListing(listing_id="b", raw_title="t", price=1, confidence=0.9)
    low = CardListing(listing_id="c", raw_title="t", price=1, set_code="base1", number="4",
                      confidence=0.3)  # fmt: skip
    reasons = review_reasons([ok, unpriced, low], {"base1-4": {}}, ["c"], 0.7)
    assert reasons == {"b": "no market price", "c": "name differs from TCGdex; low confidence"}
    write_review_sheet([ok, unpriced, low], cfg, reasons)
    rows = (tmp_path / "review.csv").read_text().splitlines()
    assert rows[0].endswith("needs_review,why,checked_ok") and rows[1].endswith("False,,")


# ---------------------------------------------------------------------------- faster search
def row(title, desc="", lid=None):
    return {"listing_id": lid or anon_id(title), "raw_title": title, "raw_description": desc,
            "condition_label": ""}  # fmt: skip


def test_prefilter_drops_the_obvious_by_title_and_keeps_anything_unclear():
    rows = [row("Charizard PSA 9 Base Set"), row("Charizard 4/102 PSA 10 worthy, raw"),
            row("Pokemon card lot 50 cards"), row("Base Set Booster Pack"),
            row("Charizard ex 151 pack fresh"), row("Japanese Charizard ex"),
            row("Charzard base set holo"), row("Charizard 151 SIR 199/165"),
            row("Blastoise 2/102", "trade for a Charizard?"), row("Mewtwo 10/102 holo")]  # fmt: skip
    kept, dropped = prefilter(rows)
    assert dropped == {"graded": 1, "is_lot": 2, "non_english": 1}
    assert [r["raw_title"] for r in kept][:2] == ["Charizard 4/102 PSA 10 worthy, raw",
                                                  "Charizard ex 151 pack fresh"]  # fmt: skip
    live, dropped = prefilter(rows, card_name="Charizard ex")
    assert dropped["other_card"] == 1  # the Mewtwo; "Charzard" and the description still count
    assert {r["raw_title"] for r in live} >= {"Charzard base set holo", "Charizard 151 SIR 199/165"}


class CountingLLM:
    """Offline extraction that counts calls and how many ran at the same time."""

    def __init__(self, llm):
        import threading

        self.llm, self.model, self.provider = llm, "fake-model", "fake"
        self.calls, self.now, self.most = 0, 0, 0
        self.lock = threading.Lock()

    def json(self, **kw):
        import time

        with self.lock:
            self.calls += 1
            self.now += 1
            self.most = max(self.most, self.now)
        time.sleep(0.05)
        try:
            return self.llm.json(**kw)
        finally:
            with self.lock:
                self.now -= 1


def test_identification_runs_batches_in_parallel_and_remembers_cards(cfg, llm, tmp_path):
    cfg["ingest"]["identified_cache"] = str(tmp_path / "identified")
    rows = [r for r in (anonymize(i) for i in RAW) if r]
    fake, stats = CountingLLM(llm), {}
    cache = IdentifiedCache(cfg)
    first = extract_cards(fake, rows, batch_size=5, log=None, parallel=4, cache=cache, stats=stats)
    assert fake.calls == -(-len(rows) // 5) and fake.most > 1  # batches ran side by side
    assert stats["from_cache"] == 0 and stats["llm_calls"] == fake.calls
    again = extract_cards(fake, rows, batch_size=5, log=None, parallel=4, cache=cache, stats=stats)
    assert again == first and stats == {**stats, "from_cache": len(rows), "llm_calls": 0}
    edited = [{**rows[0], "raw_description": "now with a crease"}, *rows[1:]]
    extract_cards(fake, edited, batch_size=5, log=None, cache=cache, stats=stats)
    assert stats["llm_calls"] == 1 and stats["from_cache"] == len(rows) - 1  # new text, new call


def test_identify_listings_reports_what_was_dropped_before_and_after_the_llm(cfg, llm, tmp_path):
    cfg["ingest"]["identified_cache"] = None
    rows = [r for r in (anonymize(i) for i in RAW) if r]
    kept, dropped, stats = identify_listings(cfg, llm, rows, log=None, card_name="Charizard")
    assert all(x.card_name.startswith("Charizard") for x in kept)
    assert stats["prefiltered"]["other_card"] > 0 and dropped["other_card"] == stats[
        "prefiltered"]["other_card"]  # fmt: skip
    assert stats["listings"] < len(rows)  # fewer listings reached the LLM
    cfg["ingest"]["llm"] = "offline"
    assert identify_listings(cfg, llm, rows[:2], log=None)[2]["model"] == cfg["models"]["offline"]
