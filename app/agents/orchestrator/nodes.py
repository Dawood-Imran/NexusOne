"""Node implementations for the NexusOne main LangGraph orchestrator."""

from __future__ import annotations

import time
from typing import Any

from app.actions.ticket_service import TicketService
from app.agents.orchestrator.action_routing import extract_ticket_request
from app.agents.orchestrator.answer_composer import AnswerComposer
from app.agents.orchestrator.routing import route_message
from app.agents.orchestrator.state import OrchestratorState
from app.agents.sql_subgraph import SQLSubgraph, clean_question_text
from app.agents.sql_subgraph.presentation import (
    format_safe_terminal_answer,
    sanitized_columns,
    sanitized_rows,
)
from app.agents.sql_subgraph.state import SQLExecutor, SQLPlanner
from app.auth.profiles import UserProfile, get_profile
from app.guardrails.policy import check_message_access
from app.retrieval.chunk_index import MetadataChunkRetriever, build_answer_from_chunks
from app.retrieval.chunk_index import ChunkSearchResult
from app.retrieval.local_kb import LocalKBRetriever, build_answer_from_results
from app.retrieval.local_kb import RetrievalResult


def append_trace(state: OrchestratorState, node_name: str, details: dict[str, Any]) -> list[dict[str, Any]]:
    trace = list(state.get("trace", []))
    trace.append({"node": node_name, "status": details.get("status"), "details": details})
    return trace


def make_load_user_context_node() -> Any:
    def load_user_context(state: OrchestratorState) -> OrchestratorState:
        started_at = state.get("started_at", time.perf_counter())
        # The authenticated HTTP path supplies the immutable session profile.
        # Trusted graph/unit callers without one retain the manifest lookup.
        provided_profile = state.get("profile")
        profile = (
            provided_profile
            if isinstance(provided_profile, UserProfile)
            else get_profile(str(state.get("user_id", "")))
        )
        clean_message = clean_question_text(str(state.get("message", "")))
        next_state: OrchestratorState = {
            **state,
            "started_at": started_at,
            "profile": profile,
            "clean_message": clean_message,
        }
        if profile is None:
            next_state["status"] = "error"
            next_state["reason_code"] = "UNKNOWN_USER"
            next_state["error_message"] = "The selected demo user could not be found."
        elif not clean_message:
            next_state["status"] = "error"
            next_state["reason_code"] = "EMPTY_MESSAGE"
            next_state["error_message"] = "Ask a company policy, process, or ticket question."
        next_state["trace"] = append_trace(
            next_state,
            "load_user_context",
            {
                "status": next_state.get("status", "running"),
                "user_found": profile is not None,
                "message_chars": len(clean_message),
                "role": getattr(profile, "role", None),
            },
        )
        return next_state

    return load_user_context


def make_precheck_guardrails_node() -> Any:
    def precheck_guardrails(state: OrchestratorState) -> OrchestratorState:
        if state.get("status") == "error":
            next_state = dict(state)
            next_state["trace"] = append_trace(
                state,
                "precheck_guardrails",
                {"status": "skipped", "reason": state.get("reason_code")},
            )
            return next_state

        profile = state["profile"]
        decision = check_message_access(profile, state["clean_message"])
        next_state: OrchestratorState = {
            **state,
            "access_decision": decision,
            "category": decision.category,
        }
        if not decision.allowed:
            next_state["status"] = "denied"
            next_state["reason_code"] = decision.reason_code
            next_state["route"] = "deny"
        next_state["trace"] = append_trace(
            next_state,
            "precheck_guardrails",
            {
                "status": next_state.get("status", "allowed"),
                "allowed": decision.allowed,
                "category": decision.category,
                "reason_code": decision.reason_code,
            },
        )
        return next_state

    return precheck_guardrails


def make_route_question_node() -> Any:
    def route_question(state: OrchestratorState) -> OrchestratorState:
        if state.get("status") in {"error", "denied"}:
            next_state = dict(state)
            next_state["route"] = "error" if state.get("status") == "error" else "deny"
            next_state["trace"] = append_trace(
                state,
                "route_question",
                {"status": "skipped", "route": next_state["route"]},
            )
            return next_state

        route = route_message(state["clean_message"])
        next_state: OrchestratorState = {**state, "route": route}
        next_state["trace"] = append_trace(
            next_state,
            "route_question",
            {"status": "routed", "route": route, "category": state.get("category")},
        )
        return next_state

    return route_question


def make_run_sql_node(executor: SQLExecutor | None, planner: SQLPlanner | None) -> Any:
    sql_graph = SQLSubgraph(executor=executor, planner=planner)

    def run_sql(state: OrchestratorState) -> OrchestratorState:
        profile = state["profile"]
        run = sql_graph.invoke_with_trace(
            {
                "conversation_id": state.get("conversation_id", "web-chat"),
                "turn_id": state.get("turn_id", "web-turn"),
                "user_id": profile.user_id,
                "question": state["clean_message"],
                "user_context": profile.to_context(),
                "execute": bool(state.get("execute_sql", executor is not None)),
            }
        )
        answer = format_safe_terminal_answer(run.output, question=state["clean_message"])
        if run.output.sql_status == "validated":
            answer = (
                "I can route this to the structured-data connector and the SQL subgraph validated a safe query. "
                "Live database execution is not enabled in local validation-only mode."
            )
        execution_status = _sql_execution_status(run.output.sql_status)
        row_count = len(run.output.sql_rows)
        sources = [
            {
                "name": source.get("name"),
                "kind": source.get("kind"),
                "domain": source.get("domain"),
            }
            for source in run.output.sql_sources
        ]
        next_state: OrchestratorState = {
            **state,
            "sql_output": run.output,
            "sql_message": answer,
            "sql_sources": sources,
            "sql_traces": run.traces,
            "sql_execution_status": execution_status,
            "sql_row_count": row_count,
            "sql_planner_backend": run.output.planner_backend,
            "sql_planner_fallback_reason": run.output.planner_fallback_reason,
        }
        next_state["trace"] = append_trace(
            next_state,
            "run_sql_subgraph",
            {
                "status": run.output.sql_status,
                "execution_status": execution_status,
                "row_count": row_count,
                "planner_backend": run.output.planner_backend,
                "planner_fallback_reason": run.output.planner_fallback_reason,
                "sources": [source["name"] for source in sources],
                "subgraph_nodes": [trace.node_name for trace in run.traces],
            },
        )
        return next_state

    return run_sql


def make_retrieve_rag_node(
    chunk_retriever: MetadataChunkRetriever | None,
    local_retriever: LocalKBRetriever | None,
) -> Any:
    chunks = chunk_retriever or MetadataChunkRetriever()
    local = local_retriever or LocalKBRetriever()

    def retrieve_rag(state: OrchestratorState) -> OrchestratorState:
        profile = state["profile"]
        if chunks.available():
            backend = chunks.backend_name()
            results = chunks.search(state["clean_message"], profile, max_results=4)
            message = build_answer_from_chunks(state["clean_message"], results)
            citations = _chunk_source_refs(results)
        else:
            backend = "local_kb"
            results = local.search(state["clean_message"], profile, max_results=3)
            message = build_answer_from_results(state["clean_message"], results)
            citations = _local_source_refs(results)

        next_state: OrchestratorState = {
            **state,
            "rag_message": message,
            "rag_citations": citations,
            "rag_result_count": len(results),
            "rag_backend": backend,
        }
        next_state["trace"] = append_trace(
            next_state,
            "retrieve_rag_context",
            {
                "status": "answered" if results else "no_answer",
                "backend": backend,
                "result_count": len(results),
                "citation_titles": [citation["title"] for citation in citations],
            },
        )
        return next_state

    return retrieve_rag


def make_run_ticket_action_node(ticket_service: TicketService | None = None) -> Any:
    service = ticket_service or TicketService()

    def run_ticket_action(state: OrchestratorState) -> OrchestratorState:
        profile = state.get("profile")
        request = extract_ticket_request(state["clean_message"])
        result = service.create_ticket(profile, request)
        next_state: OrchestratorState = {
            **state,
            "ticket_request": request,
            "ticket_result": result,
            "ticket_message": result.message,
            "status": result.status,
            "reason_code": result.reason_code or "TICKET_ACTION",
        }
        if result.ticket is not None:
            next_state["ticket"] = dict(result.ticket)
        if result.missing_fields:
            next_state["missing_fields"] = list(result.missing_fields)
        next_state["trace"] = append_trace(
            next_state,
            "run_ticket_action",
            {
                "status": result.status,
                "reason_code": result.reason_code,
                "department": request.department,
                "category": request.category,
                "priority": request.priority,
                "missing_fields": list(result.missing_fields),
                "ticket_id": result.ticket.get("ticket_id") if result.ticket else None,
            },
        )
        return next_state

    return run_ticket_action


def make_validate_answer_node() -> Any:
    def validate_answer(state: OrchestratorState) -> OrchestratorState:
        route = state.get("route")
        sql_output = state.get("sql_output")
        rag_count = int(state.get("rag_result_count", 0))
        has_sql_answer = sql_output is not None and sql_output.sql_status in {"answered", "validated"}
        has_rag_answer = rag_count > 0
        safe = True
        reason = None
        if route == "rag" and not has_rag_answer:
            reason = "NO_ACCESSIBLE_CONTEXT"
        elif route == "sql" and not has_sql_answer:
            reason = "SQL_NOT_ANSWERED"
        elif route == "combined" and not (has_sql_answer or has_rag_answer):
            reason = "NO_TOOL_ANSWER"
        elif route == "ticket_create" and state.get("status") not in {"ticket_created", "needs_clarification"}:
            reason = "TICKET_ACTION_NOT_COMPLETED"
        validation = {
            "status": "safe" if safe else "unsafe",
            "safe": safe,
            "reason": reason,
            "route": route,
            "has_sql_answer": has_sql_answer,
            "has_rag_answer": has_rag_answer,
        }
        next_state: OrchestratorState = {**state, "validation": validation}
        next_state["trace"] = append_trace(next_state, "validate_answer", validation)
        return next_state

    return validate_answer


def make_compose_final_answer_node(composer: AnswerComposer) -> Any:
    def compose_final_answer(state: OrchestratorState) -> OrchestratorState:
        route = state.get("route", "rag")
        profile = state["profile"]
        sql_output = state.get("sql_output")
        status = _response_status_for_success(state)
        context = {
            "question": state.get("clean_message"),
            "route": route,
            "status": status,
            "role": profile.role,
            "category": state.get("category"),
            "validation": state.get("validation", {}),
            "sql_answer": state.get("sql_message", ""),
            "rag_answer": state.get("rag_message", ""),
            "action_answer": state.get("ticket_message", ""),
            "citations": state.get("rag_citations", []),
            "sources": state.get("sql_sources", []),
            "sql_status": sql_output.sql_status if sql_output is not None else None,
        }
        composition = composer.compose(context)
        next_state: OrchestratorState = {
            **state,
            "final_answer": composition.answer,
            "composer_backend": composition.backend,
        }
        if composition.error:
            next_state["composer_error"] = composition.error
        if composition.fallback_reason:
            next_state["composer_fallback_reason"] = composition.fallback_reason
        next_state["trace"] = append_trace(
            next_state,
            "compose_final_answer",
            {
                "status": "composed",
                "backend": composition.backend,
                "error": composition.error,
                "fallback_reason": composition.fallback_reason,
                "answer_chars": len(composition.answer),
            },
        )
        return next_state

    return compose_final_answer


def make_finalize_response_node() -> Any:
    def finalize_response(state: OrchestratorState) -> OrchestratorState:
        profile = state.get("profile")
        started_at = float(state.get("started_at", time.perf_counter()))
        status = state.get("status")
        reason_code = state.get("reason_code")
        decision = state.get("access_decision")

        if status == "error":
            response = {
                "status": "error",
                "reason_code": reason_code,
                "route": state.get("route", "error"),
                "model_backend": None,
                "sql_execution": {"status": "not_run", "row_count": 0},
                "message": state.get("error_message", "The request could not be handled."),
                "latency_ms": _elapsed_ms(started_at),
            }
            response.update(_turn_context(state))
        elif status == "denied" and decision is not None:
            response = {
                "status": "denied",
                "reason_code": decision.reason_code,
                "category": decision.category,
                "route": "deny",
                "model_backend": None,
                "sql_execution": {"status": "not_run", "row_count": 0},
                "message": decision.message,
                "allowed_alternatives": list(decision.allowed_alternatives),
                "profile": profile.to_public_dict(),
                "latency_ms": _elapsed_ms(started_at),
            }
            response.update(_turn_context(state))
        else:
            response = _successful_response(state, started_at)

        if state.get("composer_fallback_reason"):
            response["model_fallback_reason"] = state["composer_fallback_reason"]
        if state.get("sql_output") is not None:
            response["sql_planner_backend"] = state.get("sql_planner_backend", "deterministic")
            response["sql_planner_fallback_reason"] = state.get("sql_planner_fallback_reason")

        if state.get("include_trace"):
            response["trace"] = list(state.get("trace", []))
            if state.get("sql_traces"):
                response["subgraph_trace"] = [
                    {
                        "node": trace.node_name,
                        "status": trace.details.get("status"),
                        "details": dict(trace.details),
                    }
                    for trace in state["sql_traces"]
                ]
        next_state: OrchestratorState = {**state, "response": response}
        next_state["trace"] = append_trace(
            next_state,
            "finalize_response",
            {"status": response["status"], "reason_code": response.get("reason_code")},
        )
        if state.get("include_trace"):
            next_state["response"]["trace"] = list(next_state["trace"])
        return next_state

    return finalize_response


def _successful_response(state: OrchestratorState, started_at: float) -> dict[str, Any]:
    profile = state["profile"]
    route = state.get("route", "rag")
    decision = state.get("access_decision")
    category = decision.category if decision is not None else state.get("category")
    final_answer = state.get("final_answer", "")

    if route == "sql":
        sql_output = state["sql_output"]
        return {
            "status": sql_output.sql_status,
            "reason_code": "SQL_SUBGRAPH",
            "route": route,
            "model_backend": state.get("composer_backend"),
            "category": category,
            "message": final_answer or state.get("sql_message", sql_output.sql_answer_summary),
            "rows": sanitized_rows(sql_output),
            "columns": sanitized_columns(sql_output),
            "row_count": len(sanitized_rows(sql_output)),
            "sql_execution": {
                "status": state.get("sql_execution_status", _sql_execution_status(sql_output.sql_status)),
                "row_count": len(sanitized_rows(sql_output)),
            },
            "sources": state.get("sql_sources", []),
            "profile": profile.to_public_dict(),
            "latency_ms": _elapsed_ms(started_at),
            **_turn_context(state),
        }

    if route == "combined":
        status = _response_status_for_success(state)
        safe_rows = sanitized_rows(state["sql_output"]) if state.get("sql_output") is not None else []
        return {
            "status": status,
            "reason_code": "COMBINED_GRAPH",
            "route": route,
            "model_backend": state.get("composer_backend"),
            "category": category,
            "message": final_answer,
            "citations": state.get("rag_citations", []),
            "rows": safe_rows,
            "row_count": len(safe_rows),
            "sql_execution": {
                "status": state.get("sql_execution_status", "not_run"),
                "row_count": len(safe_rows),
            },
            "sources": state.get("sql_sources", []),
            "profile": profile.to_public_dict(),
            "latency_ms": _elapsed_ms(started_at),
            **_turn_context(state),
        }

    if route == "ticket_create":
        status = state.get("status", "error")
        return {
            "status": status,
            "reason_code": state.get("reason_code"),
            "route": route,
            "model_backend": state.get("composer_backend"),
            "sql_execution": {"status": "not_run", "row_count": 0},
            "category": category,
            "message": final_answer or state.get("ticket_message", ""),
            "ticket": state.get("ticket"),
            "missing_fields": state.get("missing_fields", []),
            "profile": profile.to_public_dict(),
            "latency_ms": _elapsed_ms(started_at),
            **_turn_context(state),
        }

    has_results = int(state.get("rag_result_count", 0)) > 0
    return {
        "status": "answered" if has_results else "no_answer",
        "reason_code": "ANSWERED_FROM_GRAPH_RAG" if has_results else "NO_ACCESSIBLE_CONTEXT",
        "route": route,
        "model_backend": state.get("composer_backend"),
        "sql_execution": {"status": "not_run", "row_count": 0},
        "category": category,
        "message": final_answer or state.get("rag_message", ""),
        "citations": state.get("rag_citations", []),
        "profile": profile.to_public_dict(),
        "latency_ms": _elapsed_ms(started_at),
        **_turn_context(state),
    }


def _sql_execution_status(sql_status: str) -> str:
    if sql_status == "answered":
        return "executed"
    if sql_status == "validated":
        return "validation_only"
    if sql_status in {"error", "refused"}:
        return "error"
    return "not_executed"


def _response_status_for_success(state: OrchestratorState) -> str:
    route = state.get("route", "rag")
    if route == "sql":
        return state["sql_output"].sql_status
    if route == "combined":
        if int(state.get("rag_result_count", 0)) > 0:
            return "answered"
        return state["sql_output"].sql_status
    if route == "ticket_create":
        return state.get("status", "error")
    return "answered" if int(state.get("rag_result_count", 0)) > 0 else "no_answer"


def _turn_context(state: OrchestratorState) -> dict[str, str]:
    return {
        "conversation_id": str(state.get("conversation_id", "web-chat")),
        "turn_id": str(state.get("turn_id", "web-turn")),
    }


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _chunk_source_refs(results: tuple[ChunkSearchResult, ...]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for index, result in enumerate(results, start=1):
        payload = result.chunk.citation.to_dict()
        payload.update(
            {
                "reference_id": index,
                "label": f"[{index}]",
                "chunk_id": result.chunk.chunk_id,
                "chunk_index": result.chunk.chunk_index,
                "excerpt": result.snippet,
                "text": result.chunk.text,
            }
        )
        refs.append(payload)
    return refs


def _local_source_refs(results: tuple[RetrievalResult, ...]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for index, result in enumerate(results, start=1):
        payload = result.document.citation.to_dict()
        payload.update(
            {
                "reference_id": index,
                "label": f"[{index}]",
                "excerpt": result.snippet,
                "text": result.document.body,
            }
        )
        refs.append(payload)
    return refs
