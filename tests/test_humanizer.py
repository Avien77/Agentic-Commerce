"""Humanizer Agent: the number check, the retry with the error, and the template fallback."""

from src.agents.humanizer import build_facts, make_responding_node, number_check, template_reply
from src.agents.platform import route_after_responding
from src.llm import LLM
from src.schemas import CardListing, EvaluatedListing, LandedCostResult, ParsedQuery


def _ranked(price=52.0, delivery="in_person"):
    lc = LandedCostResult(price=price, shipping=0.0, tax=0.0, total=price, shipping_estimated=False)
    listing = CardListing(
        listing_id="x1", raw_title="Charizard NM", card_name="Charizard", set_name="Base Set",
        price=price, condition="NM", delivery_type=delivery,
    )  # fmt: skip
    return EvaluatedListing(listing=listing, landed_cost=lc, utility_score=0.9)


def _state(**kw):
    q = ParsedQuery(card_name="Charizard", budget=60.0, persona="serious_collector")
    return {"parsed_query": q, "ranked_listings": [_ranked()], **kw}


def test_number_check_catches_wrong_amounts_and_missing_names():
    assert number_check("The Charizard is $52.00 total.", [52.0], ["Charizard"]) == []
    problems = number_check("It's $50 total.", [52.0], ["Charizard"])
    assert any("$50" in p for p in problems) and any("Charizard" in p for p in problems)


def test_template_passes_its_own_number_check(cfg):
    facts = build_facts(_state(), cfg)
    assert facts["status"] == "recommend" and facts["top"]["total"] == "$52.00"
    assert number_check(template_reply(facts), [52.0], ["Charizard"]) == []


class ScriptedLLM(LLM):
    """Returns the given replies in order, like a model that gets the price wrong."""

    def __init__(self, replies):
        super().__init__(model="rules", cache_dir=None)
        self.replies = list(replies)

    def text(self, *, tag, system, prompt):
        self.prompts = [*getattr(self, "prompts", []), prompt]
        return self.replies.pop(0)


def _run_until_done(node, state, cfg):
    for _ in range(5):
        state = {**state, **node(state)}
        if route_after_responding(state, cfg["limits"]["max_humanizer_retries"]) == "DONE":
            return state
    raise AssertionError("RESPONDING did not finish")


def test_retry_with_error_then_pass(cfg):
    llm = ScriptedLLM(["Grab the Charizard for $50.", "The Charizard is $52.00, near mint."])
    out = _run_until_done(make_responding_node(cfg, llm=llm), _state(), cfg)
    assert out["final_response"] == "The Charizard is $52.00, near mint."
    assert out["humanizer_retry_count"] == 1 and out["response_source"] == "llm"
    assert "$50" in llm.prompts[1]  # the retry is told what was wrong


def test_two_failures_fall_back_to_template(cfg):
    llm = ScriptedLLM(["Only $50!", "Still $49.99!"])
    out = _run_until_done(make_responding_node(cfg, llm=llm), _state(), cfg)
    assert out["response_source"] == "template" and "$52.00" in out["final_response"]
    assert out["number_check_passed"] is True


def test_nothing_fits_explains_budget_gap(cfg):
    over = _ranked(price=65.0).model_copy(update={"rejected": True})
    state = {"parsed_query": ParsedQuery(card_name="Charizard", budget=60.0),
             "ranked_listings": [], "rejected_listings": [over], "closest_rejected": over}  # fmt: skip
    facts = build_facts(state, cfg)
    assert facts["status"] == "nothing_fits" and facts["why"] == "it is $5.00 over your budget"
