"""Consumer Agent: buyer's assistant, planner, math/ranking executor, and memory owner."""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

import diskcache

from src.config import load_config
from src.memory import BuyerMemory
from src.schemas import EvaluatedListing, ParsedQuery
from src.state import AgentState
from src.tools.landed_cost import compute_landed_cost
from src.tools.policy import evaluate_policy
from src.tools.utility import rank_listings

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "consumer"


def _parse_intent_with_gemini(
    user_input: str,
    saved_profile: dict[str, Any],
    model_id: str,
    temperature: float,
    use_cache: bool = True,
) -> ParsedQuery:
    """Call primary LLM with Pydantic structured output to parse the buyer's request."""
    from google import genai

    prompt = (
        "Parse the buyer's Pokemon TCG request into structured JSON fields.\n"
        "Rules:\n"
        "- Extract card_name, set_code (TCGdex set id if clear, e.g., 'base1'), budget (USD), "
        "min_condition (NM/LP/MP/HP/DMG), excluded_variants (e.g. ['reverse']), "
        "persona (budget_parent, serious_collector, cautious_buyer), and is_consultative.\n"
        "- If the user did not state a budget or persona in this message, leave them null/default "
        "unless clearly implied.\n"
        f"Saved buyer profile defaults (use only if omitted in request): {json.dumps(saved_profile)}\n"
        f"Buyer request: {user_input}"
    )

    cache = diskcache.Cache(str(CACHE_DIR))
    cache_key = f"intent:{model_id}:{temperature}:{hashlib.sha256(prompt.encode()).hexdigest()}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return ParsedQuery(**cached)

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": ParsedQuery,
            "temperature": temperature,
        },
    )
    parsed_dict = json.loads(response.text)
    if use_cache:
        cache.set(cache_key, parsed_dict)
    return ParsedQuery(**parsed_dict)


def make_intent_node(
    memory: Optional[BuyerMemory] = None,
    config: Optional[dict[str, Any]] = None,
    llm_parser: Optional[Callable[[str, dict[str, Any]], ParsedQuery]] = None,
    use_cache: bool = True,
) -> Callable[[AgentState], dict[str, Any]]:
    """Build the INTENT node (Consumer Agent, LLM + Memory)."""
    cfg = config or load_config()
    mem = memory or BuyerMemory()

    def intent_node(state: AgentState) -> dict[str, Any]:
        t0 = time.perf_counter()
        session_id = state.get("session_id", "default")
        user_input = state.get("user_input", "")
        clarify_answer = state.get("clarify_answer")
        combined_input = (
            f"{user_input}\nClarification answer: {clarify_answer}"
            if clarify_answer
            else user_input
        )

        saved_profile = mem.get_profile(session_id)

        if llm_parser is not None:
            parsed = llm_parser(combined_input, saved_profile)
        else:
            parsed = _parse_intent_with_gemini(
                user_input=combined_input,
                saved_profile=saved_profile,
                model_id=cfg["models"]["primary"],
                temperature=cfg["models"].get("temperature", 0.0),
                use_cache=use_cache,
            )

        # Backfill from SQLite memory if the user didn't repeat budget/persona
        updates: dict[str, Any] = {}
        if parsed.budget is None and saved_profile.get("budget") is not None:
            updates["budget"] = float(saved_profile["budget"])
        if saved_profile.get("persona") and "persona" not in combined_input.lower():
            # Keep saved persona if user didn't explicitly switch
            if parsed.persona == "cautious_buyer" and saved_profile["persona"] != "cautious_buyer":
                updates["persona"] = saved_profile["persona"]
        if parsed.min_condition is None and saved_profile.get("preferred_condition"):
            updates["min_condition"] = saved_profile["preferred_condition"]

        if updates:
            parsed = parsed.model_copy(update=updates)

        timings = dict(state.get("stage_timings", {}))
        timings["INTENT"] = round(time.perf_counter() - t0, 4)

        return {
            "current_state": "INTENT",
            "parsed_query": parsed,
            "stage_timings": timings,
        }

    return intent_node


def make_ranking_node(
    config: Optional[dict[str, Any]] = None,
) -> Callable[[AgentState], dict[str, Any]]:
    """Build the RANKING node (Consumer Agent, deterministic Python)."""
    cfg = config or load_config()

    def ranking_node(state: AgentState) -> dict[str, Any]:
        t0 = time.perf_counter()
        parsed = state.get("parsed_query")
        if parsed is None or parsed.budget is None:
            raise ValueError("RANKING requires parsed_query with a valid budget.")

        evaluated = state.get("evaluated_listings", [])
        reflection_complete = bool(state.get("reflection_complete", False))

        default_ship = float(cfg["pricing"]["default_shipping_estimate"])
        tax_rate = float(cfg["pricing"]["default_tax_rate"])
        risk_reject = float(cfg["thresholds"]["risk_reject"])
        risk_warn = float(cfg["thresholds"]["risk_warn"])

        # 1. Compute deterministic landed cost for every evaluated listing
        with_costs: list[EvaluatedListing] = []
        for item in evaluated:
            lc = compute_landed_cost(
                price=item.listing.price,
                shipping=item.listing.shipping,
                delivery_type=item.listing.delivery_type,
                default_shipping_estimate=default_ship,
                tax_rate=tax_rate,
            )
            with_costs.append(item.model_copy(update={"landed_cost": lc}))

        # 2. Enforce Platform policy rules (budget cap, risk ceiling, reflection gate)
        policy_res = evaluate_policy(
            candidates=with_costs,
            budget=parsed.budget,
            risk_reject_threshold=risk_reject,
            risk_warn_threshold=risk_warn,
            reflection_complete=reflection_complete,
        )

        # 3. Rank surviving listings with persona-weighted utility
        ranked = rank_listings(
            listings=policy_res.passing,
            budget=parsed.budget,
            persona=parsed.persona,
            config=cfg,
        )

        timings = dict(state.get("stage_timings", {}))
        timings["RANKING"] = round(time.perf_counter() - t0, 4)

        return {
            "current_state": "RANKING",
            "ranked_listings": ranked,
            "rejected_listings": policy_res.rejected,
            "closest_rejected": policy_res.closest_rejected,
            "stage_timings": timings,
        }

    return ranking_node


def make_done_node(
    memory: Optional[BuyerMemory] = None,
) -> Callable[[AgentState], dict[str, Any]]:
    """Build the DONE node (Consumer Agent, persists session memory to SQLite)."""
    mem = memory or BuyerMemory()

    def done_node(state: AgentState) -> dict[str, Any]:
        t0 = time.perf_counter()
        session_id = state.get("session_id", "default")
        parsed = state.get("parsed_query")
        ranked = state.get("ranked_listings", [])
        top_pick_id = ranked[0].listing.listing_id if ranked else None

        if parsed is not None:
            mem.save_profile(
                session_id=session_id,
                budget=parsed.budget,
                persona=parsed.persona,
                preferred_set=parsed.set_code,
                preferred_condition=parsed.min_condition,
            )
            mem.log_query(
                session_id=session_id,
                raw_query=state.get("user_input", ""),
                parsed_dict=parsed.model_dump(),
                top_pick_id=top_pick_id,
            )

        timings = dict(state.get("stage_timings", {}))
        timings["DONE"] = round(time.perf_counter() - t0, 4)

        return {
            "current_state": "DONE",
            "stage_timings": timings,
        }

    return done_node
