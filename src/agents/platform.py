"""Platform Agent (Orchestrator): CLARIFY logic, policy gates, and bounded-loop routing."""

import hashlib
import os
import time
from pathlib import Path
from typing import Any, Callable, Literal, Optional

import diskcache

from src.config import load_config
from src.schemas import ParsedQuery
from src.state import AgentState

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache" / "platform"


def needs_clarification(
    parsed: Optional[ParsedQuery], clarify_count: int, max_clarify: int = 1
) -> Optional[str]:
    """Deterministic code rule deciding whether to enter CLARIFY (Section 3).

    Returns a reason string if clarification is needed, or None to skip directly to SEARCHING.
    """
    if clarify_count >= max_clarify:
        return None
    if parsed is None:
        return "missing_card_and_budget"
    if not parsed.card_name:
        return "missing_card"
    if parsed.budget is None and not parsed.is_consultative:
        return "missing_budget"
    if parsed.set_code is None and not parsed.is_consultative and parsed.budget is None:
        return "ambiguous_printing_and_budget"
    return None


def _phrase_clarifying_question_llm(
    user_input: str,
    reason: str,
    model_id: str,
    temperature: float,
    use_cache: bool = True,
) -> str:
    """Use the primary LLM to phrase one concise, spoken-friendly clarifying question."""
    from google import genai

    prompt = (
        "You are a helpful Pokemon TCG shop assistant. Ask ONE short, natural clarifying question "
        "(under 20 words) to resolve what is missing from the buyer's request.\n"
        f"Missing reason: {reason}\n"
        f"Buyer request: {user_input}"
    )
    cache = diskcache.Cache(str(CACHE_DIR))
    cache_key = f"clarify:{model_id}:{temperature}:{hashlib.sha256(prompt.encode()).hexdigest()}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached is not None:
            return str(cached)

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config={"temperature": temperature},
    )
    question = response.text.strip()
    if use_cache:
        cache.set(cache_key, question)
    return question


def make_clarify_node(
    config: Optional[dict[str, Any]] = None,
    question_phrasing_fn: Optional[Callable[[str, str], str]] = None,
    use_cache: bool = True,
) -> Callable[[AgentState], dict[str, Any]]:
    """Build the CLARIFY node (Platform Agent: code rule + LLM wording)."""
    cfg = config or load_config()
    max_clarify = int(cfg["limits"]["max_clarify_questions"])

    def clarify_node(state: AgentState) -> dict[str, Any]:
        t0 = time.perf_counter()
        parsed = state.get("parsed_query")
        clarify_count = int(state.get("clarify_count", 0))
        reason = (
            needs_clarification(parsed, clarify_count, max_clarify=max_clarify) or "missing_details"
        )

        if question_phrasing_fn is not None:
            question = question_phrasing_fn(state.get("user_input", ""), reason)
        else:
            question = _phrase_clarifying_question_llm(
                user_input=state.get("user_input", ""),
                reason=reason,
                model_id=cfg["models"]["primary"],
                temperature=cfg["models"].get("temperature", 0.0),
                use_cache=use_cache,
            )

        timings = dict(state.get("stage_timings", {}))
        timings["CLARIFY"] = round(time.perf_counter() - t0, 4)

        return {
            "current_state": "CLARIFY",
            "clarify_count": clarify_count + 1,
            "clarifying_question": question,
            "stage_timings": timings,
        }

    return clarify_node


# --- LangGraph Conditional Edge Routers (Platform Agent) ---


def route_after_intent(
    state: AgentState,
    max_clarify: int = 1,
) -> Literal["CLARIFY", "SEARCHING"]:
    """Route to CLARIFY if request is unclear and clarify_count < max_clarify; else SEARCHING."""
    reason = needs_clarification(
        state.get("parsed_query"),
        clarify_count=int(state.get("clarify_count", 0)),
        max_clarify=max_clarify,
    )
    return "CLARIFY" if reason is not None else "SEARCHING"


def route_after_evaluating(
    state: AgentState,
    risk_reject_threshold: float = 0.6,
    max_search_retries: int = 1,
) -> Literal["SEARCHING", "RANKING"]:
    """Only EVALUATING can send work backward to SEARCHING, and at most once (Section 3)."""
    evaluated = state.get("evaluated_listings", [])
    surviving = [item for item in evaluated if item.risk_score < risk_reject_threshold]
    retries = int(state.get("search_retry_count", 0))

    if not surviving and retries < max_search_retries:
        return "SEARCHING"
    return "RANKING"


def route_after_responding(
    state: AgentState,
    max_humanizer_retries: int = 1,
) -> Literal["RESPONDING", "DONE"]:
    """If Humanizer number check fails, retry once; otherwise proceed to DONE."""
    passed = bool(state.get("number_check_passed", False))
    retries = int(state.get("humanizer_retry_count", 0))
    if not passed and retries <= max_humanizer_retries:
        return "RESPONDING"
    return "DONE"
