from pathlib import Path

from src.agents.consumer import make_done_node, make_intent_node, make_ranking_node
from src.agents.platform import (
    make_clarify_node,
    route_after_evaluating,
    route_after_intent,
)
from src.graph import build_graph
from src.memory import BuyerMemory
from src.schemas import CardListing, EvaluatedListing, ParsedQuery


def test_route_after_intent_clarifies_once_when_budget_missing():
    parsed_no_budget = ParsedQuery(card_name="Charizard", budget=None)
    assert route_after_intent({"parsed_query": parsed_no_budget, "clarify_count": 0}) == "CLARIFY"
    assert route_after_intent({"parsed_query": parsed_no_budget, "clarify_count": 1}) == "SEARCHING"

    parsed_clear = ParsedQuery(card_name="Charizard", budget=60.0)
    assert route_after_intent({"parsed_query": parsed_clear, "clarify_count": 0}) == "SEARCHING"


def test_route_after_evaluating_retries_once_when_all_flagged():
    scam = EvaluatedListing(
        listing=CardListing(listing_id="scam1", raw_title="Cheap Zard", price=10.0),
        risk_score=0.85,
    )
    assert (
        route_after_evaluating({"evaluated_listings": [scam], "search_retry_count": 0})
        == "SEARCHING"
    )
    assert (
        route_after_evaluating({"evaluated_listings": [scam], "search_retry_count": 1}) == "RANKING"
    )


def test_end_to_end_graph_with_memory_and_ranking(tmp_path: Path):
    mem = BuyerMemory(db_path=tmp_path / "buyer.sqlite")

    def fake_parser(text: str, saved: dict) -> ParsedQuery:
        return ParsedQuery(
            card_name="Charizard",
            set_code="base1",
            budget=60.0,
            persona="serious_collector",
        )

    def fake_eval(state):
        return {
            "current_state": "EVALUATING",
            "reflection_complete": True,
            "evaluated_listings": [
                EvaluatedListing(
                    listing=CardListing(
                        listing_id="fb_cheap_hp",
                        raw_title="Charizard HP",
                        card_name="Charizard",
                        price=25.0,
                        condition="HP",
                        delivery_type="in_person",
                    ),
                    risk_score=0.1,
                ),
                EvaluatedListing(
                    listing=CardListing(
                        listing_id="fb_clean_nm",
                        raw_title="Charizard NM",
                        card_name="Charizard",
                        price=52.0,
                        condition="NM",
                        delivery_type="in_person",
                    ),
                    risk_score=0.05,
                ),
                EvaluatedListing(
                    listing=CardListing(
                        listing_id="fb_scam",
                        raw_title="Charizard Zelle Only",
                        card_name="Charizard",
                        price=15.0,
                        condition="NM",
                        delivery_type="shipping",
                    ),
                    risk_score=0.95,
                ),
            ],
        }

    app = build_graph(
        memory=mem,
        intent_node=make_intent_node(memory=mem, llm_parser=fake_parser),
        clarify_node=make_clarify_node(question_phrasing_fn=lambda q, r: "What is your budget?"),
        evaluating_node=fake_eval,
        ranking_node=make_ranking_node(),
        done_node=make_done_node(memory=mem),
    )

    result = app.invoke(
        {
            "session_id": "pablo_test",
            "user_input": "Base Set Charizard under $60, I care about condition",
            "clarify_count": 0,
            "search_retry_count": 0,
            "humanizer_retry_count": 0,
        }
    )

    # Serious collector should pick NM over HP, and scam must be rejected
    assert result["current_state"] == "DONE"
    assert result["ranked_listings"][0].listing.listing_id == "fb_clean_nm"
    assert len(result["rejected_listings"]) == 1
    assert result["rejected_listings"][0].listing.listing_id == "fb_scam"

    # Memory should persist budget and persona for future turns
    saved = mem.get_profile("pablo_test")
    assert saved["budget"] == 60.0
    assert saved["persona"] == "serious_collector"
