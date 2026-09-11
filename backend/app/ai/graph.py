"""The LangGraph graph wiring the three tools together.

Deliberately small and acyclic: each of `extract_complaint`, `edit_complaint`
and `assess_complaint` is a single node, and the graph's only job is routing
one invocation to the right node from a shared entry point based on
`intent`. There is no agentic loop here - nothing in this phase needs the
model to plan a sequence of tool calls - so the failure mode CLAUDE.md warns
about ("an unbounded agent loop is the one thing that can genuinely drain the
budget") does not arise structurally.

`settings.ai_recursion_limit` is still passed on *every* invocation
regardless (see `_invoke` below), because that is the rule this codebase
holds itself to, not a judgement call about whether this particular graph
happens to need it - a future node that introduces a real loop inherits the
guard for free instead of someone having to remember to add it.
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.ai.tools.assess import assess_complaint
from app.ai.tools.edit import edit_complaint
from app.ai.tools.extract import extract_complaint
from app.core.config import get_settings
from app.schemas.complaint import (
    AIAssessment,
    ComplaintUpdate,
    ExtractedComplaint,
    FieldProvenance,
)


class ComplaintAIState(TypedDict, total=False):
    """Shared state threaded through the graph.

    Only the keys relevant to the requested `intent` are ever populated by a
    given run; the rest are absent, not `None` - `total=False` is what makes
    that legal.
    """

    intent: Literal["extract", "edit", "assess"]

    # extract
    text: str
    extracted: ExtractedComplaint

    # edit
    existing: dict[str, Any]
    instruction: str
    update: ComplaintUpdate
    update_provenance: list[FieldProvenance]

    # assess
    complaint: dict[str, Any]
    assessment: AIAssessment


def _extract_node(state: ComplaintAIState) -> dict[str, Any]:
    return {"extracted": extract_complaint(state["text"])}


def _edit_node(state: ComplaintAIState) -> dict[str, Any]:
    update, provenance = edit_complaint(state["existing"], state["instruction"])
    return {"update": update, "update_provenance": provenance}


def _assess_node(state: ComplaintAIState) -> dict[str, Any]:
    return {"assessment": assess_complaint(state["complaint"])}


def _route(state: ComplaintAIState) -> str:
    return state["intent"]


def _build_graph() -> CompiledStateGraph:
    graph = StateGraph(ComplaintAIState)
    graph.add_node("extract", _extract_node)
    graph.add_node("edit", _edit_node)
    graph.add_node("assess", _assess_node)

    graph.add_conditional_edges(
        START, _route, {"extract": "extract", "edit": "edit", "assess": "assess"}
    )
    graph.add_edge("extract", END)
    graph.add_edge("edit", END)
    graph.add_edge("assess", END)
    return graph.compile()


_GRAPH = _build_graph()


def _invoke(state: ComplaintAIState) -> ComplaintAIState:
    """Every entry point into the graph goes through here, so
    `recursion_limit` can never be forgotten at a call site."""
    settings = get_settings()
    result = _GRAPH.invoke(dict(state), config={"recursion_limit": settings.ai_recursion_limit})
    # `.invoke()` is typed against the compiled graph's generic state protocol,
    # not literally `ComplaintAIState` - this cast just restates what every
    # node above already guarantees about the shape of what comes back.
    return cast(ComplaintAIState, result)


def run_extract(text: str) -> ExtractedComplaint:
    result = _invoke({"intent": "extract", "text": text})
    return result["extracted"]


def run_edit(
    existing: dict[str, Any], instruction: str
) -> tuple[ComplaintUpdate, list[FieldProvenance]]:
    result = _invoke({"intent": "edit", "existing": existing, "instruction": instruction})
    return result["update"], result["update_provenance"]


def run_assess(complaint: dict[str, Any]) -> AIAssessment:
    result = _invoke({"intent": "assess", "complaint": complaint})
    return result["assessment"]


__all__ = ["ComplaintAIState", "run_assess", "run_edit", "run_extract"]
