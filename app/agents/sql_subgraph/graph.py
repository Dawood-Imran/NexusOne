"""Standalone SQL subgraph runner with a bounded repair loop."""

from __future__ import annotations

import re
from dataclasses import asdict, replace
from typing import Any, Mapping

from app.agents.sql_subgraph.nodes import (
    build_schema_context,
    check_answer_grounding,
    classify_sql_intent,
    draft_sql,
    ensure_output,
    execute_or_package,
    finalize_repair_failure,
    load_user_context,
    repair_sql,
    select_sources,
    validate_candidate_sql,
)
from app.agents.sql_subgraph.state import (
    SQLExecutor,
    SQLNodeTrace,
    SQLPlanner,
    SQLSubgraphInput,
    SQLSubgraphOutput,
    SQLSubgraphRun,
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
    "record_validation_feedback",
    "repair_sql",
    "execute_or_package",
    "record_execution_feedback",
    "check_answer_grounding",
    "record_answer_feedback",
    "finalize_repair_failure",
)

GRAPH_EDGES = (
    ("START", "load_user_context"),
    ("load_user_context", "classify_sql_intent"),
    ("classify_sql_intent", "select_allowed_sources"),
    ("select_allowed_sources", "build_schema_context"),
    ("build_schema_context", "draft_sql"),
    ("draft_sql", "validate_sql_safety"),
    ("validate_sql_safety", "execute_or_package"),
    ("validate_sql_safety", "record_validation_feedback"),
    ("record_validation_feedback", "repair_sql"),
    ("execute_or_package", "check_answer_grounding"),
    ("execute_or_package", "record_execution_feedback"),
    ("record_execution_feedback", "repair_sql"),
    ("check_answer_grounding", "record_answer_feedback"),
    ("record_answer_feedback", "repair_sql"),
    ("repair_sql", "validate_sql_safety"),
    ("validate_sql_safety", "finalize_repair_failure"),
    ("check_answer_grounding", "END"),
    ("finalize_repair_failure", "END"),
)

TERMINAL_STATUSES = {"refused", "no_allowed_source", "needs_clarification", "error"}


def clean_question_text(question: str) -> str:
    cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", question)
    cleaned = re.sub(r"\^\[\[[0-9;]*[A-Za-z]", "", cleaned)
    cleaned = cleaned.replace("^[[D", "").replace("^[[C", "").replace("^[[A", "").replace("^[[B", "")
    return " ".join(cleaned.strip().split())


class SQLSubgraph:
    """Independent SQL subgraph with an invoke-style API."""

    def __init__(self, executor: SQLExecutor | None = None, planner: SQLPlanner | None = None) -> None:
        self.executor = executor
        self.planner = planner
        self.planner_backend = str(getattr(planner, "provider_name", "deterministic"))
        self.planner_fallback_reason = getattr(planner, "fallback_reason", None)

    def invoke(self, payload: SQLSubgraphInput | Mapping[str, Any]) -> SQLSubgraphOutput:
        return self.invoke_with_trace(payload).output

    def invoke_with_trace(self, payload: SQLSubgraphInput | Mapping[str, Any]) -> SQLSubgraphRun:
        request = _coerce_input(payload)
        state = SQLSubgraphState(
            conversation_id=request.conversation_id,
            turn_id=request.turn_id,
            user_id=request.user_id,
            question=clean_question_text(request.sql_question or request.question),
            requested_intent=request.requested_intent,
            user_context=request.user_context,
            execute=request.execute,
            planner_backend=self.planner_backend,
        )

        traces: list[SQLNodeTrace] = []

        for node_name, node in (
            ("load_user_context", lambda current: load_user_context(current, self.executor)),
            ("classify_sql_intent", lambda current: classify_sql_intent(current, self.planner)),
            ("select_allowed_sources", select_sources),
            ("build_schema_context", build_schema_context),
            ("draft_sql", lambda current: draft_sql(current, self.planner)),
        ):
            state = node(state)
            traces.append(SQLNodeTrace(node_name=node_name, details=_trace_details(state)))
            if _has_terminal_output(state):
                return SQLSubgraphRun(output=self._output_with_provider_metadata(state), traces=tuple(traces))

        while True:
            state = validate_candidate_sql(state)
            traces.append(SQLNodeTrace(node_name="validate_sql_safety", details=_trace_details(state)))

            if state.validation is None or not state.validation.is_safe:
                if _can_repair(state):
                    traces.append(SQLNodeTrace(node_name="record_validation_feedback", details=_trace_details(state)))
                    state = repair_sql(state, self.planner)
                    traces.append(SQLNodeTrace(node_name="repair_sql", details=_trace_details(state)))
                    continue
                state = finalize_repair_failure(state)
                traces.append(SQLNodeTrace(node_name="finalize_repair_failure", details=_trace_details(state)))
                break

            state = execute_or_package(state, self.executor)
            traces.append(SQLNodeTrace(node_name="execute_or_package", details=_trace_details(state)))

            if state.output is not None and state.output.sql_status == "error":
                if _can_repair(state):
                    traces.append(SQLNodeTrace(node_name="record_execution_feedback", details=_trace_details(state)))
                    state = repair_sql(state, self.planner)
                    traces.append(SQLNodeTrace(node_name="repair_sql", details=_trace_details(state)))
                    continue
                state = finalize_repair_failure(state)
                traces.append(SQLNodeTrace(node_name="finalize_repair_failure", details=_trace_details(state)))
                break

            state = check_answer_grounding(state)
            traces.append(SQLNodeTrace(node_name="check_answer_grounding", details=_trace_details(state)))
            if state.answer_feedback:
                if _can_repair(state):
                    traces.append(SQLNodeTrace(node_name="record_answer_feedback", details=_trace_details(state)))
                    state = repair_sql(state, self.planner)
                    traces.append(SQLNodeTrace(node_name="repair_sql", details=_trace_details(state)))
                    continue
                state = finalize_repair_failure(state)
                traces.append(SQLNodeTrace(node_name="finalize_repair_failure", details=_trace_details(state)))
            break

        return SQLSubgraphRun(output=self._output_with_provider_metadata(state), traces=tuple(traces))

    def _output_with_provider_metadata(self, state: SQLSubgraphState) -> SQLSubgraphOutput:
        output = ensure_output(state)
        fallback_reason = self.planner_fallback_reason
        if state.planner_error:
            fallback_reason = f"OPENAI_SQL_PLANNER_RUNTIME_ERROR_{_safe_error_name(state.planner_error)}"
        return replace(
            output,
            planner_backend=self.planner_backend,
            planner_fallback_reason=fallback_reason,
        )

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
        try:
            user_context = UserContext(
                user_id=str(user_context["user_id"]),
                role=str(user_context["role"]),
                department=str(user_context["department"]),
                location=str(user_context["location"]),
                groups=tuple(user_context.get("groups", ())),
                status=str(user_context.get("status", "active")),
            )
        except (KeyError, TypeError, ValueError):
            # Treat malformed context as absent. The executor then resolves the
            # authenticated identity by its bound parameter or refuses safely.
            user_context = None

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


def _has_terminal_output(state: SQLSubgraphState) -> bool:
    return state.output is not None and state.output.sql_status in TERMINAL_STATUSES


def _can_repair(state: SQLSubgraphState) -> bool:
    return state.repair_attempts < state.max_repair_attempts


def _trace_details(state: SQLSubgraphState) -> dict[str, Any]:
    validation = state.validation
    execution = state.execution_result
    output = state.output
    user_context = state.user_context

    details: dict[str, Any] = {
        "status": output.sql_status if output is not None else "running",
        "intent": state.sql_intent,
        "allowed_sources": [source.name for source in state.allowed_sources],
        "schema_context_chars": len(state.schema_context),
        "parameter_keys": sorted(state.sql_parameters.keys()),
        "repair_attempts": state.repair_attempts,
        "repair_reasons": list(state.repair_history),
        "final_answer_grounded": state.final_answer_grounded,
    }
    if user_context is not None:
        details["user"] = {
            "role": user_context.role,
            "department": user_context.department,
            "location": user_context.location,
            "status": user_context.status,
        }
    if validation is not None:
        details["validation"] = {
            "is_safe": validation.is_safe,
            "reason": validation.reason,
            "used_sources": list(validation.used_sources),
        }
    if execution is not None:
        details["execution"] = {
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
    note = state.planner_error or state.error_message
    if note:
        details["internal_note"] = note
    details["planner_backend"] = state.planner_backend
    return details


def _safe_error_name(note: str) -> str:
    """Keep provider fallback metadata to a class-like safe identifier."""

    match = re.search(r"failed:\s*([A-Za-z_][A-Za-z0-9_]*)", note)
    return (match.group(1) if match else "UNKNOWN").upper()
