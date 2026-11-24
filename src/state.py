"""Shared LangGraph state interface and tool signatures (Section 3 & 10)."""

from typing import Literal, Optional, TypedDict

from src.schemas import CardListing, EvaluatedListing, ParsedQuery

GraphStage = Literal[
    "INTENT",
    "CLARIFY",
    "SEARCHING",
    "EVALUATING",
    "RANKING",
    "RESPONDING",
    "DONE",
]


class AgentState(TypedDict, total=False):
    """Typed state shared across Platform, Consumer, Merchant, and Humanizer agents."""

    # Input & session tracking
    session_id: str
    user_input: str
    current_state: GraphStage

    # Consumer Agent (INTENT)
    parsed_query: Optional[ParsedQuery]

    # Platform Agent (CLARIFY)
    clarify_count: int
    clarifying_question: Optional[str]
    clarify_answer: Optional[str]

    # Merchant Agent (SEARCHING & EVALUATING)
    search_retry_count: int
    relaxed_filters: bool
    candidate_listings: list[CardListing]
    evaluated_listings: list[EvaluatedListing]
    reflection_complete: bool

    # Platform & Consumer Agents (Policy & RANKING)
    ranked_listings: list[EvaluatedListing]
    rejected_listings: list[EvaluatedListing]
    closest_rejected: Optional[EvaluatedListing]

    # Humanizer Agent (RESPONDING)
    humanizer_retry_count: int
    draft_response: Optional[str]
    number_check_passed: bool
    number_check_error: Optional[str]
    final_response: Optional[str]

    # Telemetry & logging
    stage_timings: dict[str, float]
    token_usage: dict[str, int]
