"""Merchant Agent: search filters, the risk score, reflection and the price check."""

from src.agents.merchant import (
    distinct_printings,
    find,
    make_evaluating_node,
    make_searching_node,
    name_matches,
    price_check_facts,
)
from src.schemas import ParsedQuery
from src.tools.prices import pick_variant_price
from src.tools.risk import assess, match_flags


def test_name_match_is_strict_about_suffixes():
    assert name_matches("charizard", "Charizard ex", 85)
    assert not name_matches("pikachu vmax", "Pikachu", 85)
    assert not name_matches("charizard", "unknown", 85)


def test_find_applies_set_condition_and_variant_filters(data, cfg):
    q = ParsedQuery(card_name="Charizard", set_code="base1", budget=400, min_condition="LP")
    ids = {x.listing_id for x in find(data.listings, q, cfg)}
    assert ids == {"S01", "S02", "S04"}  # HP, unknown-condition and 151 cards are filtered out
    relaxed = {x.listing_id for x in find(data.listings, q, cfg, relaxed=True)}
    assert {"S03", "S09"} <= relaxed
    no_reverse = ParsedQuery(card_name="Pikachu", excluded_variants=["normal"])
    assert all(x.variant != "normal" for x in find(data.listings, no_reverse, cfg))


def test_distinct_printings(data, cfg):
    assert len(distinct_printings(data.listings, "Charizard", cfg)) == 2
    assert len(distinct_printings(data.listings, "Mewtwo", cfg)) == 1


def test_red_flags_respect_negation(data):
    assert [f.id for f in match_flags("zelle only, ships fast", data.red_flags)] == ["RF-01"]
    assert not match_flags("this is not a proxy, real card", data.red_flags)


def test_risk_scores_traps_and_decoys(data, cfg, listing):
    trap = assess(listing("S02"), data.prices, data.red_flags, cfg)  # Zelle only, 14% of market
    assert trap.decision == "reject" and trap.r_price == 1.0 and trap.r_text == 1.0
    decoy = assess(listing("S03"), data.prices, data.red_flags, cfg)  # honest heavily played
    assert decoy.decision == "ok"
    clean = assess(listing("S04"), data.prices, data.red_flags, cfg)
    assert clean.risk == 0.0


def test_pick_variant_price():
    v = {"normal": 2.0, "reverseHolofoil": 5.0, "holofoil": 9.0}
    assert pick_variant_price(v, "reverse") == 5.0
    assert pick_variant_price(v, "holo") == 9.0
    assert pick_variant_price(v, None) == 2.0
    assert pick_variant_price({}, "holo") is None


def test_search_and_evaluate_nodes(data, cfg, llm):
    q = ParsedQuery(card_name="Charizard", set_code="Base Set", budget=400)
    search = make_searching_node(data, cfg)
    out = search({"parsed_query": q, "current_state": "INTENT"})
    assert out["search_retry_count"] == 0 and not out["relaxed_filters"]
    ev = make_evaluating_node(data, cfg, llm=llm)({**out, "parsed_query": q})
    assert ev["reflection_complete"] is True
    by_id = {x.listing.listing_id: x for x in ev["evaluated_listings"]}
    assert by_id["S02"].risk_score >= 0.6 and by_id["S02"].warning  # explained
    assert by_id["S04"].warning is None and by_id["S04"].market_price == 380.0
    retry = search({"parsed_query": q, "current_state": "EVALUATING", "search_retry_count": 0})
    assert retry["search_retry_count"] == 1 and retry["relaxed_filters"]


def test_reflection_off_is_ablation_3(data, cfg, llm, listing):
    node = make_evaluating_node(data, cfg, llm=llm, reflect=False)
    out = node({"candidate_listings": [listing("S02")], "parsed_query": ParsedQuery()})
    assert out["evaluated_listings"][0].risk_score == 0.0


def test_price_check_facts(data, cfg):
    q = ParsedQuery(
        card_name="Mewtwo", set_code="Base Set", is_consultative=True, asked_price=45,
        min_condition="LP",
    )  # fmt: skip
    f = price_check_facts(q, data, cfg)
    assert f["found"] and f["market_for_condition"] == 34.0 and f["verdict"] == "on the high side"
    assert price_check_facts(ParsedQuery(card_name="Lugia"), data, cfg)["found"] is False
