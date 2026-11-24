"""LangGraph 7-state orchestration graph (Section 3 & 8).

States: INTENT -> CLARIFY (optional) -> SEARCHING -> EVALUATING -> RANKING -> RESPONDING -> DONE
Bounded loops:
  1. INTENT -> CLARIFY (at most 1 question) -> INTENT (once user answers) or pause
  2. EVALUATING -> SEARCHING (at most 1 retry with relaxed filters if 0 listings survive)
  3. RESPONDING -> RESPONDING (at most 1 retry if number check fails, then template fallback)
"""

from pathlib import Path
from typing import Any, Callable, Optional

from langgraph.graph import END, START, StateGraph

from src.agents.consumer import make_done_node, make_intent_node, make_ranking_node
from src.agents.platform import (
    make_clarify_node,
    route_after_evaluating,
    route_after_intent,
    route_after_responding,
)
from src.config import load_config
from src.memory import BuyerMemory
from src.state import AgentState


def _default_searching_stub(state: AgentState) -> dict[str, Any]:
    """Placeholder for Merchant Agent SEARCHING node until Merchant Agent is implemented."""
    retries = int(state.get("search_retry_count", 0))
    relaxed = bool(state.get("relaxed_filters", False))
    if state.get("current_state") == "EVALUATING":
        retries += 1
        relaxed = True
    return {
        "current_state": "SEARCHING",
        "search_retry_count": retries,
        "relaxed_filters": relaxed,
        "candidate_listings": state.get("candidate_listings", []),
    }


def _default_evaluating_stub(state: AgentState) -> dict[str, Any]:
    """Placeholder for Merchant Agent EVALUATING node until Merchant Agent is implemented."""
    return {
        "current_state": "EVALUATING",
        "evaluated_listings": state.get("evaluated_listings", []),
        "reflection_complete": True,
    }


def _default_responding_stub(state: AgentState) -> dict[str, Any]:
    """Placeholder for Humanizer Agent RESPONDING node until Humanizer Agent is implemented."""
    ranked = state.get("ranked_listings", [])
    closest = state.get("closest_rejected")
    if ranked:
        top = ranked[0]
        total = top.landed_cost.total if top.landed_cost else top.listing.price
        reply = (
            f"Hi, I'm an AI assistant. My top pick is {top.listing.card_name} "
            f"at ${total:.2f} total."
        )
    elif closest is not None:
        total = closest.landed_cost.total if closest.landed_cost else closest.listing.price
        reply = (
            f"Hi, I'm an AI assistant. Nothing passed all rules. The closest option is "
            f"{closest.listing.card_name} at ${total:.2f}, rejected because {closest.rejection_reason}."
        )
    else:
        reply = "Hi, I'm an AI assistant. No matching listings were found."

    return {
        "current_state": "RESPONDING",
        "draft_response": reply,
        "final_response": reply,
        "number_check_passed": True,
    }


def build_graph(
    config: Optional[dict[str, Any]] = None,
    memory: Optional[BuyerMemory] = None,
    intent_node: Optional[Callable[[AgentState], dict[str, Any]]] = None,
    clarify_node: Optional[Callable[[AgentState], dict[str, Any]]] = None,
    searching_node: Optional[Callable[[AgentState], dict[str, Any]]] = None,
    evaluating_node: Optional[Callable[[AgentState], dict[str, Any]]] = None,
    ranking_node: Optional[Callable[[AgentState], dict[str, Any]]] = None,
    responding_node: Optional[Callable[[AgentState], dict[str, Any]]] = None,
    done_node: Optional[Callable[[AgentState], dict[str, Any]]] = None,
    pause_on_clarify: bool = True,
):
    """Compile and return the LangGraph StateGraph.

    Set pause_on_clarify=True for interactive CLI / scripted clarify turns (CLARIFY -> END so the
    caller can collect clarify_answer and re-enter INTENT).
    """
    cfg = config or load_config()
    mem = memory or BuyerMemory()

    max_clarify = int(cfg["limits"]["max_clarify_questions"])
    max_search_retries = int(cfg["limits"]["max_search_retries"])
    max_humanizer_retries = int(cfg["limits"]["max_humanizer_retries"])
    risk_reject = float(cfg["thresholds"]["risk_reject"])

    graph = StateGraph(AgentState)

    graph.add_node("INTENT", intent_node or make_intent_node(memory=mem, config=cfg))
    graph.add_node("CLARIFY", clarify_node or make_clarify_node(config=cfg))
    graph.add_node("SEARCHING", searching_node or _default_searching_stub)
    graph.add_node("EVALUATING", evaluating_node or _default_evaluating_stub)
    graph.add_node("RANKING", ranking_node or make_ranking_node(config=cfg))
    graph.add_node("RESPONDING", responding_node or _default_responding_stub)
    graph.add_node("DONE", done_node or make_done_node(memory=mem))

    graph.add_edge(START, "INTENT")

    graph.add_conditional_edges(
        "INTENT",
        lambda s: route_after_intent(s, max_clarify=max_clarify),
        {"CLARIFY": "CLARIFY", "SEARCHING": "SEARCHING"},
    )

    if pause_on_clarify:
        graph.add_edge("CLARIFY", END)
    else:
        graph.add_edge("CLARIFY", "SEARCHING")

    graph.add_edge("SEARCHING", "EVALUATING")

    graph.add_conditional_edges(
        "EVALUATING",
        lambda s: route_after_evaluating(
            s,
            risk_reject_threshold=risk_reject,
            max_search_retries=max_search_retries,
        ),
        {"SEARCHING": "SEARCHING", "RANKING": "RANKING"},
    )

    graph.add_edge("RANKING", "RESPONDING")

    graph.add_conditional_edges(
        "RESPONDING",
        lambda s: route_after_responding(s, max_humanizer_retries=max_humanizer_retries),
        {"RESPONDING": "RESPONDING", "DONE": "DONE"},
    )

    graph.add_edge("DONE", END)

    return graph.compile()


def export_architecture_diagram(output_path: Path | str = "docs/architecture.png") -> Path:
    """Export the LangGraph Mermaid architecture figure for the report (Section 8)."""
    compiled = build_graph()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    png_bytes = compiled.get_graph().draw_mermaid_png()
    out.write_bytes(png_bytes)
    return out
