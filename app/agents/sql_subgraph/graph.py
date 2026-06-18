"""Standalone SQL subgraph runner.

This module does not require the parent graph. It exposes an invoke-style API
that can later be wrapped as a LangGraph node.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from app.agents.sql_subgraph.nodes import (
    build_schema_context,
    classify_sql_intent,
    draft_sql,
    ensure_output,
    execute_or_package,
    load_user_context,
    select_sources,
    validate_candidate_sql,
)
from app.agents.sql_subgraph.state import (
    SQLExecutor,
    SQLNodeTrace,
    SQLPlanner,
    SQLSubgraphRun,
    SQLSubgraphInput,
    SQLSubgraphOutput,
    SQLSubgraphState,
    UserContext,
)


GRAPH_NODES = (
    "load_user_context",
    "classify_sql_intent",
    "select_allowed_sources",
    "build_schema_context",
    "draft_sql",
    "validate_sql_safety",
    "execute_or_package",
)

GRAPH_EDGES = (
    ("START", "load_user_context"),
    ("load_user_context", "classify_sql_intent"),
    ("classify_sql_intent", "select_allowed_sources"),
    ("select_allowed_sources", "build_schema_context"),
    ("build_schema_context", "draft_sql"),
    ("draft_sql", "validate_sql_safety"),
    ("validate_sql_safety", "execute_or_package"),
    ("execute_or_package", "END"),
)


class SQLSubgraph:
    """Independent SQL subgraph with an invoke-style API."""

    def __init__(self, executor: SQLExecutor | None = None, planner: SQLPlanner | None = None) -> None:
        self.executor = executor
        self.planner = planner

    def invoke(self, payload: SQLSubgraphInput | Mapping[str, Any]) -> SQLSubgraphOutput:
        return self.invoke_with_trace(payload).output

    def invoke_with_trace(self, payload: SQLSubgraphInput | Mapping[str, Any]) -> SQLSubgraphRun:
        request = _coerce_input(payload)
        state = SQLSubgraphState(
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
            user_id=request.user_id,
            question=request.sql_question or request.question,
            requested_intent=request.requested_intent,
            user_context=request.user_context,
            execute=request.execute,
        )

        traces: list[SQLNodeTrace] = []
        for node_name, node in (
            ("load_user_context", lambda current: load_user_context(current, self.executor)),
            ("classify_sql_intent", lambda current: classify_sql_intent(current, self.planner)),
            ("select_allowed_sources", select_sources),
            ("build_schema_context", build_schema_context),
            ("draft_sql", lambda current: draft_sql(current, self.planner)),
            ("validate_sql_safety", validate_candidate_sql),
            ("execute_or_package", lambda current: execute_or_package(current, self.executor)),
        ):
            state = node(state)
            traces.append(SQLNodeTrace(node_name=node_name, details=_trace_details(state)))
            if state.output is not None and state.sql_status in {
                "refused",
                "no_allowed_source",
                "needs_clarification",
                "error",
            }:
                break

        return SQLSubgraphRun(output=ensure_output(state), traces=tuple(traces))

    def graph_definition(self) -> dict[str, tuple[str, ...] | tuple[tuple[str, str], ...]]:
        return {"nodes": GRAPH_NODES, "edges": GRAPH_EDGES}


def run_sql_subgraph(
    payload: SQLSubgraphInput | Mapping[str, Any],
    executor: SQLExecutor | None = None,
    planner: SQLPlanner | None = None,
) -> SQLSubgraphOutput:
    return SQLSubgraph(executor=executor, planner=planner).invoke(payload)


def _coerce_input(payload: SQLSubgraphInput | Mapping[str, Any]) -> SQLSubgraphInput:
    if isinstance(payload, SQLSubgraphInput):
        return payload

    user_context = payload.get("user_context")
    if isinstance(user_context, Mapping):
        user_context = UserContext(
            user_id=str(user_context["user_id"]),
            role=str(user_context["role"]),
            department=str(user_context["department"]),
            location=str(user_context["location"]),
            groups=tuple(user_context.get("groups", ())),
            status=str(user_context.get("status", "active")),
        )

    return SQLSubgraphInput(
        conversation_id=str(payload.get("conversation_id", "standalone")),
        turn_id=str(payload.get("turn_id", "turn-1")),
        user_id=str(payload["user_id"]),
        question=str(payload["question"]),
        sql_question=payload.get("sql_question"),  # type: ignore[arg-type]
        requested_intent=payload.get("requested_intent"),  # type: ignore[arg-type]
        user_context=user_context,  # type: ignore[arg-type]
        execute=bool(payload.get("execute", True)),
    )


def as_dict(output: SQLSubgraphOutput) -> dict[str, Any]:
    return asdict(output)


def _trace_details(state: SQLSubgraphState) -> dict[str, Any]:
    validation = state.validation
    execution = state.execution_result
    output = state.output
    user_context = state.user_context

    details: dict[str, Any] = {
        "status": output.sql_status if output is not None else "running",
        "intent": state.sql_intent,
        "candidate_sql": state.candidate_sql,
        "parameters": dict(state.sql_parameters),
        "allowed_sources": [source.name for source in state.allowed_sources],
        "schema_context_chars": len(state.schema_context),
    }
    if user_context is not None:
        details["user"] = {
            "user_id": user_context.user_id,
            "role": user_context.role,
            "department": user_context.department,
            "location": user_context.location,
            "groups": list(user_context.groups),
            "status": user_context.status,
        }
    if validation is not None:
        details["validation"] = {
            "is_safe": validation.is_safe,
            "reason": validation.reason,
            "used_sources": list(validation.used_sources),
            "sql_to_execute": validation.sql_to_execute,
        }
    if execution is not None:
        details["execution"] = {
            "columns": list(execution.columns),
            "row_count": execution.row_count,
            "elapsed_ms": execution.elapsed_ms,
        }
    if output is not None:
        details["output"] = {
            "status": output.sql_status,
            "summary": output.sql_answer_summary,
            "row_count": len(output.sql_rows),
            "denied_reason": output.sql_denied_reason,
            "error": output.sql_error,
        }
    if state.error_message:
        details["internal_note"] = state.error_message
    return details
