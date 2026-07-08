"""Visualization-only LangGraph graph for the SQL repair subgraph."""

from __future__ import annotations

from typing import TypedDict


class VisualizationState(TypedDict, total=False):
    question: str


def _same(state: VisualizationState) -> VisualizationState:
    return state


def build_sql_repair_visualization_graph():
    """Build a LangGraph graph that mirrors the independent repair-loop flow."""

    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(VisualizationState)
    for node in (
        "load_user_context",
        "classify_sql_intent",
        "select_allowed_sources",
        "build_schema_context",
        "draft_sql",
        "validate_sql_safety",
        "record_validation_feedback",
        "repair_sql",
        "execute_or_package",
        "record_execution_feedback",
        "check_answer_grounding",
        "record_answer_feedback",
        "finalize_repair_failure",
    ):
        graph.add_node(node, _same)

    graph.add_edge(START, "load_user_context")
    graph.add_edge("load_user_context", "classify_sql_intent")
    graph.add_edge("classify_sql_intent", "select_allowed_sources")
    graph.add_edge("select_allowed_sources", "build_schema_context")
    graph.add_edge("build_schema_context", "draft_sql")
    graph.add_edge("draft_sql", "validate_sql_safety")
    graph.add_edge("validate_sql_safety", "execute_or_package")
    graph.add_edge("validate_sql_safety", "record_validation_feedback")
    graph.add_edge("record_validation_feedback", "repair_sql")
    graph.add_edge("execute_or_package", "check_answer_grounding")
    graph.add_edge("execute_or_package", "record_execution_feedback")
    graph.add_edge("record_execution_feedback", "repair_sql")
    graph.add_edge("check_answer_grounding", "record_answer_feedback")
    graph.add_edge("record_answer_feedback", "repair_sql")
    graph.add_edge("repair_sql", "validate_sql_safety")
    graph.add_edge("validate_sql_safety", "finalize_repair_failure")
    graph.add_edge("check_answer_grounding", END)
    graph.add_edge("finalize_repair_failure", END)
    return graph.compile()
