"""Live search (notebook 04) without network: each request scrapes Marketplace (here a replay
of the 28 sample raw listings) and picks the best of those fresh listings, reporting progress."""

import json
import time

import pytest

from src.config import ROOT
from src.graph import ChatSession, build_graph
from src.pipeline import PriceBook, ReplayScraper
from tests.test_pipeline_offline import FakeTCGdex

RAW_FILE = ROOT / "data/samples/sample_raw_listings.json"


class CountingReplay(ReplayScraper):
    def __init__(self, path, delay=0.0):
        super().__init__(path)
        self.calls, self.delay = 0, delay

    def search(self, terms, limit, max_charge_usd, **kw):
        self.calls += 1
        self.terms, self.limit, self.cap = terms, limit, max_charge_usd
        time.sleep(self.delay)
        return super().search(terms, limit, max_charge_usd, **kw)


@pytest.fixture
def live_cfg(cfg, tmp_path):
    cfg["merchant"]["live"] = True
    cfg["merchant"]["live_listings"] = str(tmp_path / "live_listings.json")
    for key in ("prices", "tcgdex_sets"):
        cfg["data"][key] = str(tmp_path / f"{key}.json")
    return cfg


@pytest.fixture
def make_live(live_cfg, llm, data, memory):
    def make(delay=0.0):
        from src.agents.merchant import make_searching_node

        scraper = CountingReplay(RAW_FILE, delay)
        book = PriceBook(live_cfg, {}, client=FakeTCGdex())
        node = make_searching_node(data, live_cfg, live=True, llm=llm, scraper=scraper,
                                   pricebook=book)  # fmt: skip
        app = build_graph(live_cfg, memory=memory, llm=llm, data=data, searching_node=node)
        return app, scraper

    return make


def test_each_request_picks_from_its_own_fresh_listings(make_live, live_cfg, llm):
    app, scraper = make_live()
    events = []
    chat = ChatSession(app, "live", live_cfg, llm=llm)
    _, state = chat.send(
        "Base Set Charizard under $400", on_task=lambda n, p, _info: events.append((n, p))
    )
    assert scraper.calls == 1 and scraper.terms == ["pokemon charizard base set"]
    assert scraper.limit == live_cfg["merchant"]["live_limit"] == 100
    assert scraper.cap == live_cfg["merchant"]["live_max_charge_usd"]
    live = state["live_search"]
    assert live["scraped"] == 28 and live["kept"] > 0
    ranked = state["ranked_listings"]
    assert ranked and all(x.listing.listing_id.startswith("fb_") for x in ranked)  # not samples
    assert all(x.listing.card_name == "Charizard" for x in ranked)
    assert ranked[0].market_price == 400.0  # the TCGdex price, not the sample price
    assert ranked[0].reasons  # spoken reasons for the pick
    order = [e for e in events if e[1] == "progress" or e == ("EVALUATING", "start")]
    assert order == [("searching", "progress"), ("scraped", "progress"),
                     ("identified", "progress"), ("EVALUATING", "start")]  # fmt: skip
    saved = json.loads((ROOT / live_cfg["merchant"]["live_listings"]).read_text())
    assert {x["listing_id"] for x in saved} >= {x.listing.listing_id for x in ranked}


def test_the_same_search_again_is_not_scraped_again(make_live, live_cfg, llm):
    app, scraper = make_live()
    chat = ChatSession(app, "live", live_cfg, llm=llm)
    chat.send("Base Set Charizard under $400")
    _, state = chat.send("Base Set Charizard under $350")
    assert scraper.calls == 1 and state["live_search"]["scraped"] == 28


def test_replay_scraper_returns_the_saved_items_up_to_the_limit():
    assert len(ReplayScraper(RAW_FILE).search(["anything"], limit=5, max_charge_usd=0)) == 5


def test_live_prices_never_start_from_the_sample_prices(live_cfg, llm, data, monkeypatch, tmp_path):
    from src.agents import merchant

    (tmp_path / "prices.json").write_text(json.dumps({"base1-4": {"name": "Charizard"},
                                                      "_meta": {}}))  # fmt: skip
    seen = {}

    class Book(PriceBook):
        def __init__(self, config, prices, client=None):
            seen["prices"] = dict(prices)
            super().__init__(config, prices, client=FakeTCGdex())

    monkeypatch.setattr(merchant, "PriceBook", Book)
    node = merchant.make_searching_node(data, live_cfg, live=True, llm=llm,
                                        scraper=CountingReplay(RAW_FILE))  # fmt: skip
    assert data.source == "samples"
    node({"parsed_query": merchant.ParsedQuery(card_name="Charizard", set_code="Base Set")})
    assert seen["prices"] == {"base1-4": {"name": "Charizard"}}  # data/prices.json, no samples
