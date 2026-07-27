"""State and output objects for the main NexusOne orchestrator graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, TypedDict

from app.agents.sql_subgraph.state import SQLNodeTrace, SQLSubgraphOutput
from app.guardrails.policy import AccessDecision


RouteName = Literal["rag", "sql", "combined", "ticket_create", "deny", "error"]


class OrchestratorState(TypedDict, total=False):
    conversation_id: str
    turn_id: str
    user_id: str
    message: str
    include_trace: bool
    execute_sql: bool

    profile: Any
    clean_message: str
    access_decision: AccessDecision
    route: RouteName
    category: str

    rag_message: str
    rag_citations: list[dict[str, Any]]
    rag_result_count: int
    rag_backend: str

    sql_output: SQLSubgraphOutput
    sql_message: str
    sql_sources: list[dict[str, Any]]
    sql_traces: tuple[SQLNodeTrace, ...]
    sql_execution_status: str
    sql_row_count: int
    sql_planner_backend: str
    sql_planner_fallback_reason: str | None

    ticket_request: Any
    ticket_result: Any
    ticket_message: str
    ticket: dict[str, Any]
    missing_fields: list[str]

    validation: dict[str, Any]
    final_answer: str
    composer_backend: str
    composer_error: str
    composer_fallback_reason: str
    response: dict[str, Any]
    status: str
    reason_code: str
    error_message: str
    trace: list[dict[str, Any]]
    started_at: float


@dataclass(frozen=True)
class OrchestratorRun:
    """Public result returned by the main graph wrapper."""

    response: Mapping[str, Any]
    trace: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
