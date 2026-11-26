"""The 5-part listing score (notebook 01): deal against the market, condition, trust,
convenience, identification confidence, weighted per buyer type, with spoken reasons."""

from datetime import date

import pytest

from src.schemas import CardListing, EvaluatedListing, LandedCostResult
from src.tools.utility import rank_listings, score_listing, score_parts

TODAY = date(2026, 11, 25)


def item(lid="a", total=100.0, market=None, condition="NM", risk=0.0, **listing):
    x = CardListing(listing_id=lid, raw_title=f"Card {lid}", price=total, condition=condition,
                    delivery_type=listing.pop("delivery_type", "in_person"), **listing)  # fmt: skip
    lc = LandedCostResult(price=total, shipping=0, tax=0, total=total, shipping_estimated=False)
    return EvaluatedListing(listing=x, market_price=market, risk_score=risk, landed_cost=lc)


def test_deal_compares_the_total_with_the_market_price_for_its_condition(cfg):
    parts = lambda total: score_parts(item(total=total, market=100.0), None, cfg, TODAY)[0]
    assert parts(70)["deal"] == 1.0 and parts(100)["deal"] == 0.5 and parts(130)["deal"] == 0.0
    lp = score_parts(item(total=85, market=100.0, condition="LP"), None, cfg, TODAY)[0]
    assert lp["deal"] == 0.5  # $85 is the market price for lightly played (0.85 x $100)
    # without a market price the budget is the yardstick, as in the plan formula
    assert score_parts(item(total=25), 100.0, cfg, TODAY)[0]["deal"] == 0.75


def test_reasons_say_why_and_never_praise_a_suspicious_price(cfg):
    good = score_listing(item(total=75, market=100.0, photo_count=5, public_meetup=True,
                              distance_miles=8.0), None, "budget_parent", cfg, TODAY)  # fmt: skip
    # the 3 strongest for a budget parent: price first
    assert good.reasons == ["25% under the market price", "a public meetup offered", "near mint"]
    near = score_listing(item(total=100, market=100.0, condition="MP", distance_miles=8.0),
                         None, "budget_parent", cfg, TODAY)  # fmt: skip
    assert near.reasons == ["pickup about 8 miles away"]
    cheap = score_listing(item(total=40, market=100.0), None, "budget_parent", cfg, TODAY)
    assert not any("market" in r for r in cheap.reasons)  # 40%: the risk score's job
    assert cheap.score_parts["deal"] == 0.5  # and no extra points for it


def test_trust_uses_listing_signals_and_scam_risk(cfg):
    def trust(**kw):
        return score_parts(item(**kw), None, cfg, TODAY)[0]["trust"]

    solid = trust(photo_count=6, public_meetup=True, listed_at="2026-11-20",
                  raw_description="Pack fresh, sleeved since opening, can meet at the mall.")  # fmt: skip
    bare = trust(photo_count=1)
    assert solid > bare
    assert trust(photo_count=6, pending=True) < trust(photo_count=6)
    assert trust(photo_count=6, listed_at="2026-06-01") < trust(
        photo_count=6, listed_at="2026-11-01"
    )
    assert trust(risk=0.5) < trust(risk=0.0)


def test_convenience_by_pickup_distance(cfg):
    def conv(**kw):
        return score_parts(item(**kw), None, cfg, TODAY)[0]["convenience"]

    assert conv(distance_miles=5) == 1.0 and conv(distance_miles=25) == 0.7
    assert conv(distance_miles=50) == 0.4 and conv(distance_miles=90) == 0.2
    assert conv() == cfg["scoring"]["convenience_unknown"]


def test_buyer_types_weigh_the_parts_differently(cfg):
    cheap_worn = item("worn", total=40, market=120.0, condition="HP", distance_miles=5)
    mint = item("mint", total=110, market=100.0, condition="NM", distance_miles=5)
    assert (
        rank_listings([mint, cheap_worn], None, "budget_parent", cfg)[0].listing.listing_id
        == "worn"
    )
    assert (
        rank_listings([cheap_worn, mint], None, "serious_collector", cfg)[0].listing.listing_id
        == "mint"
    )
    risky = item("risky", total=80, market=100.0, risk=0.5)
    safe = item("safe", total=95, market=100.0, photo_count=4, public_meetup=True)
    assert rank_listings([risky, safe], None, "cautious_buyer", cfg)[0].listing.listing_id == "safe"


def test_scores_and_parts_are_kept_on_the_listing(cfg):
    (top,) = rank_listings([item(total=75, market=100.0)], 200.0, "cautious_buyer", cfg, TODAY)
    assert 0 < top.utility_score <= 1 and set(top.score_parts) == {
        "deal", "condition", "trust", "convenience", "confidence"
    }  # fmt: skip


def test_the_plan_formula_is_still_available(cfg):
    cfg["scoring"]["method"] = "plan"
    (top,) = rank_listings([item(total=50, condition="NM")], 100.0, "budget_parent", cfg)
    assert top.utility_score == pytest.approx(0.70 * 0.5 + 0.15 * 1.0 + 0.15 * 1.0)
    assert top.score_parts == {} and top.reasons == []
