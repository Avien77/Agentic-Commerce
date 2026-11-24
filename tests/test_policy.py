import pytest

from src.schemas import CardListing, EvaluatedListing, LandedCostResult
from src.tools.policy import (
    PolicyViolationError,
    enforce_number_check_before_speech,
    enforce_reflection_before_ranking,
    evaluate_policy,
)


def _make_candidate(listing_id: str, total: float, risk: float) -> EvaluatedListing:
    return EvaluatedListing(
        listing=CardListing(
            listing_id=listing_id,
            raw_title=f"Card {listing_id}",
            price=total,
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


def test_policy_rejects_over_budget_and_high_risk():
    ok = _make_candidate("ok", total=55.0, risk=0.1)
    warn = _make_candidate("warn", total=50.0, risk=0.45)
    over_budget = _make_candidate("over", total=65.0, risk=0.0)
    scam = _make_candidate("scam", total=20.0, risk=0.6)

    res = evaluate_policy([ok, warn, over_budget, scam], budget=60.0)

    passing_ids = {x.listing.listing_id for x in res.passing}
    rejected_ids = {x.listing.listing_id for x in res.rejected}
    assert passing_ids == {"ok", "warn"}
    assert rejected_ids == {"over", "scam"}

    warn_item = next(x for x in res.passing if x.listing.listing_id == "warn")
    assert warn_item.warning is not None


def test_policy_empty_passing_returns_closest_rejected():
    far_over = _make_candidate("far_over", total=120.0, risk=0.0)
    near_over = _make_candidate("near_over", total=65.0, risk=0.1)
    scam_cheap = _make_candidate("scam", total=15.0, risk=0.9)

    res = evaluate_policy([far_over, near_over, scam_cheap], budget=60.0)
    assert res.passing == []
    assert res.closest_rejected is not None
    assert res.closest_rejected.listing.listing_id == "near_over"
    assert "exceeds budget" in (res.closest_rejected.rejection_reason or "")


def test_policy_execution_order_guards():
    with pytest.raises(PolicyViolationError):
        enforce_reflection_before_ranking(False)
    with pytest.raises(PolicyViolationError):
        enforce_number_check_before_speech(False)
    with pytest.raises(PolicyViolationError):
        evaluate_policy([], budget=50.0, reflection_complete=False)
