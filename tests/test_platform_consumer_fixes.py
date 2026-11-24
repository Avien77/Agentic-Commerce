"""Regression tests for the three bugs found in review: persona memory, consultative
questions without a budget, and the printing question."""

from src.agents.consumer import IntentExtraction, apply_memory, make_intent_node
from src.agents.platform import make_clarify_node, needs_clarification
from src.schemas import ParsedQuery


def test_stated_persona_beats_saved_persona(memory):
    memory.save_profile("s", budget=50, persona="budget_parent")
    node = make_intent_node(
        memory=memory,
        llm_parser=lambda t, s: IntentExtraction(card_name="Mewtwo", persona="cautious_buyer"),
    )
    parsed = node({"session_id": "s", "user_input": "Mewtwo, I don't want to get scammed"})[
        "parsed_query"
    ]
    assert parsed.persona == "cautious_buyer" and parsed.budget == 50.0
    assert parsed.filled_from_memory == ["budget"]


def test_unstated_persona_comes_from_memory():
    saved = {"persona": "serious_collector", "budget": 80.0}
    assert apply_memory(IntentExtraction(card_name="Mew"), saved).persona == "serious_collector"
    assert apply_memory(ParsedQuery(card_name="Mew"), saved).persona == "serious_collector"
    assert apply_memory(IntentExtraction(card_name="Mew"), {}).persona == "cautious_buyer"


def test_printing_question_when_several_printings_match():
    q = ParsedQuery(card_name="Charizard", budget=100)
    two = ["Charizard from Base Set", "Charizard ex from 151"]
    assert needs_clarification(q, 0, 1, printings=two) == "ambiguous_printing"
    assert needs_clarification(q.model_copy(update={"set_code": "base1"}), 0, 1, two) is None
    assert needs_clarification(q.model_copy(update={"any_printing": True}), 0, 1, two) is None
    assert needs_clarification(q, 1, 1, printings=two) is None  # only one question


def test_clarify_question_names_the_printings(cfg, llm):
    node = make_clarify_node(
        cfg, llm=llm, printings_fn=lambda q: ["Charizard from Base Set", "Charizard ex from 151"]
    )
    out = node({"parsed_query": ParsedQuery(card_name="Charizard"), "user_input": "a Charizard"})
    assert "Base Set" in out["clarifying_question"] and "151" in out["clarifying_question"]
    assert out["clarify_count"] == 1
