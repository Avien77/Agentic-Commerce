import pytest

from src.schemas import CardListing, EvaluatedListing, LandedCostResult
from src.tools.utility import compute_utility, rank_listings


def _make_item(
    listing_id: str,
    total: float,
    condition: str,
    risk: float,
) -> EvaluatedListing:
    return EvaluatedListing(
        listing=CardListing(
            listing_id=listing_id,
            raw_title=f"Card {listing_id}",
            price=total,
            condition=condition,
        ),
        risk_score=risk,
        landed_cost=LandedCostResult(
            price=total,
            shipping=0.0,
            tax=0.0,
            total=total,
            shipping_estimated=False,
        ),
    )


def test_persona_weights_shift_rankings():
    # Cheap worn card vs pricier NM card
    cheap_worn = _make_item("cheap_hp", total=20.0, condition="HP", risk=0.1)
    pricy_nm = _make_item("pricy_nm", total=50.0, condition="NM", risk=0.1)

    budget_ranked = rank_listings([cheap_worn, pricy_nm], budget=60.0, persona="budget_parent")
    assert budget_ranked[0].listing.listing_id == "cheap_hp"

    collector_ranked = rank_listings(
        [cheap_worn, pricy_nm], budget=60.0, persona="serious_collector"
    )
    assert collector_ranked[0].listing.listing_id == "pricy_nm"


def test_cautious_buyer_prefers_lower_risk():
    risky_cheap = _make_item("risky", total=30.0, condition="LP", risk=0.5)
    safe_mid = _make_item("safe", total=38.0, condition="LP", risk=0.0)

    ranked = rank_listings([risky_cheap, safe_mid], budget=60.0, persona="cautious_buyer")
    assert ranked[0].listing.listing_id == "safe"


def test_tie_goes_to_lower_landed_cost():
    # Craft two items with identical utility but different totals (budget=100, cautious_buyer)
    # Item A: total=50 (P=0.5), C=0.8 (LP), risk=0.0 (T=1.0) -> U = 0.25*0.5 + 0.25*0.8 + 0.50*1.0 = 0.825
    # Item B: total=30 (P=0.7), C=0.6 (MP), risk=0.0 (T=1.0) -> U = 0.25*0.7 + 0.25*0.6 + 0.50*1.0 = 0.825
    item_a = _make_item("higher_total", total=50.0, condition="LP", risk=0.0)
    item_b = _make_item("lower_total", total=30.0, condition="MP", risk=0.0)

    ranked = rank_listings([item_a, item_b], budget=100.0, persona="cautious_buyer")
    assert ranked[0].utility_score == ranked[1].utility_score
    assert ranked[0].listing.listing_id == "lower_total"


def test_compute_utility_clips_price_and_rejects_zero_budget():
    with pytest.raises(ValueError):
        compute_utility(total=10.0, budget=0.0, condition="NM", risk=0.0, persona="budget_parent")
    u = compute_utility(
        total=120.0, budget=100.0, condition="NM", risk=0.0, persona="budget_parent"
    )
    # P clips to 0.0 -> U = 0.70*0 + 0.15*1.0 + 0.15*1.0 = 0.30
    assert u == pytest.approx(0.30)
