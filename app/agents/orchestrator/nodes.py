"""Node implementations for the NexusOne main LangGraph orchestrator."""

from __future__ import annotations

import time
from typing import Any

from langgraph.config import get_stream_writer

from app.actions.ticket_service import TicketService
from app.agents.orchestrator.action_routing import extract_ticket_request
from app.agents.orchestrator.answer_composer import AnswerComposer, AnswerComposition, compose_with_streaming
from app.agents.orchestrator.intent_classifier import IntentClassifier, classify_request
from app.agents.orchestrator.knowledge import (
    NO_APPROVED_TICKET_GUIDANCE_MESSAGE,
    build_local_general_answer,
    build_ticket_guidance_answer,
    casual_response,
    retained_ticket_guidance_results,
    sanitize_ticket_guidance_source_text,
)
from app.agents.orchestrator.routing import route_from_intent
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
from app.retrieval.chunk_index import ChunkSearchResult, MetadataChunkRetriever, build_answer_from_chunks
from app.retrieval.config import NO_REFERENCE_MESSAGE, SOURCE_SIMILARITY_THRESHOLD
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


def make_route_question_node(classifier: IntentClassifier) -> Any:
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

        # Approval/edit routing is determined by server-held ticket workflow
        # state, never by model intent or a client-provided identity.
        workflow = state.get("ticket_workflow")
        if workflow in {"approve", "deny", "edit", "create"}:
            next_state: OrchestratorState = {
                **state,
                "route": "ticket_create",
                "intent": "ticket_create",
                "intent_confidence": 1.0,
                "needs_clarification": False,
                "clarification_question": "",
                "missing_context": [],
                "intent_reason_code": "SERVER_TICKET_WORKFLOW",
                "classifier_version": "server-ticket-workflow-v1",
            }
            next_state["trace"] = append_trace(
                next_state,
                "route_question",
                {"status": "server_workflow", "route": "ticket_create", "workflow": workflow},
            )
            return next_state

        result = classify_request(
            classifier,
            state.get("clean_message", ""),
            conversation_context=_classification_context(state),
            active_ticket_draft=None,
        )
        route = route_from_intent(result)
        next_state: OrchestratorState = {
            **state,
            "route": route,
            "intent_result": result,
            "intent": result.intent,
            "intent_confidence": result.confidence,
            "needs_clarification": result.needs_clarification,
            "clarification_question": result.clarification_question or "",
            "missing_context": list(result.missing_context),
            "intent_reason_code": result.reason_code,
            "classifier_version": result.classifier_version,
        }
        next_state["trace"] = append_trace(
            next_state,
            "route_question",
            {
                "status": "routed" if result.reason_code == "INTENT_CLASSIFIED" else "safe_failure",
                "route": route,
                "intent": result.intent,
                "confidence": result.confidence,
                "needs_clarification": result.needs_clarification,
                "reason_code": result.reason_code,
                "classifier_version": result.classifier_version,
            },
        )
        return next_state

    return route_question


def make_recheck_guardrails_node() -> Any:
    """Re-run policy after classification, before any protected route."""

    def recheck_guardrails(state: OrchestratorState) -> OrchestratorState:
        if state.get("status") in {"error", "denied"}:
            next_state = dict(state)
            next_state["trace"] = append_trace(
                state,
                "recheck_guardrails",
                {"status": "skipped", "reason": state.get("reason_code")},
            )
            return next_state

        profile = state["profile"]
        decision = check_message_access(profile, state["clean_message"])
        next_state: OrchestratorState = {**state, "access_decision": decision, "category": decision.category}
        if not decision.allowed:
            next_state["status"] = "denied"
            next_state["reason_code"] = decision.reason_code
            next_state["route"] = "deny"
        next_state["trace"] = append_trace(
            next_state,
            "recheck_guardrails",
            {
                "status": "allowed" if decision.allowed else "denied",
                "allowed": decision.allowed,
                "category": decision.category,
                "reason_code": decision.reason_code,
            },
        )
        return next_state

    return recheck_guardrails


def make_respond_feedback_node() -> Any:
    def respond_feedback(state: OrchestratorState) -> OrchestratorState:
        message = "Thanks for the feedback. Use the helpful or not helpful control on the answer so it can be recorded safely."
        next_state: OrchestratorState = {
            **state,
            "feedback_message": message,
            "status": "answered",
            "reason_code": "FEEDBACK_GUIDANCE",
        }
        next_state["trace"] = append_trace(
            next_state,
            "respond_feedback",
            {"status": "answered", "route": "feedback"},
        )
        return next_state

    return respond_feedback


def make_respond_clarification_node() -> Any:
    def respond_clarification(state: OrchestratorState) -> OrchestratorState:
        memory_message = _memory_lookup_answer(state)
        message = memory_message or state.get("clarification_question") or "Could you clarify what you would like me to help with?"
        answered_from_memory = memory_message is not None and not memory_message.startswith("I do not have that detail")
        next_state: OrchestratorState = {
            **state,
            "clarification_message": message,
            "status": "answered" if answered_from_memory else ("no_answer" if memory_message else "needs_clarification"),
            "reason_code": "LONG_TERM_MEMORY" if answered_from_memory else ("LONG_TERM_MEMORY_EMPTY" if memory_message else state.get("intent_reason_code") or "INTENT_NEEDS_CLARIFICATION"),
        }
        next_state["trace"] = append_trace(
            next_state,
            "respond_clarification",
            {"status": next_state["status"], "route": "clarification"},
        )
        return next_state

    return respond_clarification


def make_respond_unsupported_node() -> Any:
    def respond_unsupported(state: OrchestratorState) -> OrchestratorState:
        if state.get("intent") == "history_lookup":
            history = state.get("short_term_history", [])
            if history:
                recent = [item.get("user_message", "")[:240] for item in history[-3:] if item.get("user_message")]
                message = "Earlier in this conversation, you asked: " + "; ".join(f'“{item}”' for item in recent)
                status = "answered"
                reason_code = "SHORT_TERM_MEMORY"
            else:
                message = "There are no earlier turns in this conversation yet."
                status = "unsupported"
                reason_code = "SHORT_TERM_MEMORY_EMPTY"
        else:
            message = (
                "I cannot help with that request here. You can ask about company policies, general questions, "
                "knowledge lookups, ticket creation or status, or send feedback."
            )
            status = "unsupported"
            reason_code = "UNSUPPORTED_REQUEST"
        next_state: OrchestratorState = {
            **state,
            "unsupported_message": message,
            "history_message": message if state.get("intent") == "history_lookup" else "",
            "status": status,
            "reason_code": reason_code,
        }
        next_state["trace"] = append_trace(
            next_state,
            "respond_unsupported",
            {"status": status, "route": "unsupported", "reason_code": reason_code},
        )
        return next_state

    return respond_unsupported


def make_respond_casual_node() -> Any:
    def respond_casual(state: OrchestratorState) -> OrchestratorState:
        message = casual_response(state["clean_message"]) or "Hi! How can I help you today?"
        next_state: OrchestratorState = {
            **state,
            "casual_message": message,
            "status": "answered",
            "reason_code": "CASUAL",
        }
        next_state["trace"] = append_trace(
            next_state,
            "deterministic_casual_response",
            {"status": "answered", "route": "CASUAL"},
        )
        return next_state

    return respond_casual


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
        guidance_route = state.get("route") == "ticket_guidance"
        if chunks.available():
            backend = chunks.backend_name()
            retrieval_query = (
                "ticket creation guide supported teams categories required information confirmation next steps"
                if guidance_route
                else state["clean_message"]
            )
            results = chunks.search(retrieval_query, profile, max_results=4)
            threshold = chunks.config.source_similarity_threshold
            guidance_results = (
                retained_ticket_guidance_results(results, threshold=threshold)
                if guidance_route
                else results
            )
            message = (
                build_ticket_guidance_answer(guidance_results, threshold=threshold)
                if guidance_route
                else build_answer_from_chunks(state["clean_message"], results, threshold=threshold)
            )
            citations = _chunk_source_refs(
                guidance_results,
                threshold=threshold,
                sanitize_source_text=guidance_route,
            )
        else:
            backend = "local_kb"
            retrieval_query = (
                "ticket creation guide supported teams categories required information confirmation next steps"
                if guidance_route
                else state["clean_message"]
            )
            results = local.search(retrieval_query, profile, max_results=3)
            threshold = local.similarity_threshold
            guidance_results = (
                retained_ticket_guidance_results(results, threshold=threshold)
                if guidance_route
                else results
            )
            message = (
                build_ticket_guidance_answer(guidance_results, threshold=threshold)
                if guidance_route
                else build_answer_from_results(state["clean_message"], results, threshold=threshold)
            )
            citations = _local_source_refs(
                guidance_results,
                threshold=threshold,
                sanitize_source_text=guidance_route,
            )

        # Count only the retained citation set. This defensive second filter
        # keeps custom retrievers from smuggling below-threshold context into
        # composition even if their search implementation is misconfigured.
        reference_status = "sufficient" if citations else "none_reached_threshold"
        next_state: OrchestratorState = {
            **state,
            "rag_message": message,
            "rag_citations": citations,
            "rag_result_count": len(citations),
            "rag_backend": backend,
            "rag_threshold": threshold,
            "rag_reference_status": reference_status,
        }
        next_state["trace"] = append_trace(
            next_state,
            "retrieve_rag_context",
            {
                "status": "answered" if citations else "no_reference",
                "backend": backend,
                "route": state.get("route"),
                "result_count": len(citations),
                "reference_status": reference_status,
                "source_similarity_threshold": threshold,
                "score_scale": "0-100",
                "citation_titles": [citation["title"] for citation in citations],
                "sources": _bounded_source_metadata(citations),
            },
        )
        return next_state

    return retrieve_rag


def make_run_ticket_action_node(ticket_service: TicketService | None = None) -> Any:
    service = ticket_service or TicketService()

    def run_ticket_action(state: OrchestratorState) -> OrchestratorState:
        profile = state.get("profile")
        workflow = state.get("ticket_workflow")
        conversation_id = str(state.get("conversation_id", "web-chat"))
        request = extract_ticket_request(state["clean_message"])
        if workflow == "approve":
            result = service.approve_ticket(
                profile,
                conversation_id=conversation_id,
                approval_id=state.get("ticket_approval_id") or None,
            )
        elif workflow == "deny":
            result = service.deny_ticket(profile, conversation_id=conversation_id)
        else:
            result = service.preview_ticket(profile, request, conversation_id=conversation_id)
        next_state: OrchestratorState = {
            **state,
            "ticket_request": request,
            "ticket_result": result,
            "ticket_message": result.message,
            "status": result.status,
            "reason_code": result.reason_code or "TICKET_ACTION",
            "ticket_approval_required": result.status == "needs_approval",
        }
        if result.ticket is not None:
            next_state["ticket"] = dict(result.ticket)
        if result.ticket_preview is not None:
            next_state["ticket_preview"] = dict(result.ticket_preview)
        if result.missing_fields:
            next_state["missing_fields"] = list(result.missing_fields)
        next_state["trace"] = append_trace(
            next_state,
            "run_ticket_action",
            {
                "status": result.status,
                "reason_code": result.reason_code,
                "workflow": workflow or "preview",
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
            reason = "NO_SUFFICIENTLY_RELEVANT_REFERENCE"
        elif route == "ticket_guidance" and not has_rag_answer:
            reason = "NO_APPROVED_TICKET_GUIDANCE_REFERENCE"
        elif route == "sql" and not has_sql_answer:
            reason = "SQL_NOT_ANSWERED"
        elif route == "combined" and not (has_sql_answer or has_rag_answer):
            reason = "NO_TOOL_ANSWER"
        elif route == "ticket_create" and state.get("status") not in {
            "ticket_created",
            "needs_approval",
            "needs_clarification",
            "not_created",
            "denied",
        }:
            reason = "TICKET_ACTION_NOT_COMPLETED"
        elif route == "CASUAL" and not state.get("casual_message"):
            reason = "CASUAL_RESPONSE_NOT_COMPLETED"
        elif route == "feedback" and not state.get("feedback_message"):
            reason = "FEEDBACK_RESPONSE_NOT_COMPLETED"
        elif route == "clarification" and not state.get("clarification_message"):
            reason = "CLARIFICATION_RESPONSE_NOT_COMPLETED"
        elif route == "unsupported" and not state.get("unsupported_message"):
            reason = "UNSUPPORTED_RESPONSE_NOT_COMPLETED"
        elif route == "GENERAL_KNOWLEDGE" and not state.get("final_answer"):
            reason = "GENERAL_KNOWLEDGE_NOT_COMPOSED"
        validation = {
            "status": "safe" if safe else "unsafe",
            "safe": safe,
            "reason": reason,
            "route": route,
            "has_sql_answer": has_sql_answer,
            "has_rag_answer": has_rag_answer,
            "reference_status": state.get("rag_reference_status", "not_used"),
            "reference_threshold": state.get("rag_threshold"),
            "has_casual_answer": bool(state.get("casual_message")),
            "has_feedback_answer": bool(state.get("feedback_message")),
            "has_clarification_answer": bool(state.get("clarification_message")),
            "has_unsupported_answer": bool(state.get("unsupported_message")),
            "has_general_answer": bool(state.get("final_answer")),
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
        rag_result_count = int(state.get("rag_result_count", 0))
        reference_status = state.get("rag_reference_status", "not_used")
        if route == "GENERAL_KNOWLEDGE":
            local_answer = build_local_general_answer(state.get("clean_message", ""))
        elif route == "memory":
            local_answer = _memory_lookup_answer(state)
            if local_answer is None and state.get("memory_update", {}).get("status") in {"updated", "pending_model_tool"}:
                local_answer = "I saved that explicit detail to your personal profile memory."
        else:
            local_answer = None
        status = _response_status_for_success(state)
        context = {
            "question": state.get("clean_message"),
            "route": route,
            "status": status,
            "role": profile.role,
            "category": state.get("category"),
            "validation": state.get("validation", {}),
            "sql_answer": state.get("sql_message", ""),
            # A below-threshold result is never passed as factual context.
            "rag_answer": state.get("rag_message", "") if rag_result_count else "",
            "reference_status": reference_status,
            "reference_threshold": state.get("rag_threshold"),
            "reference_note": NO_REFERENCE_MESSAGE if reference_status == "none_reached_threshold" else "",
            "action_answer": state.get("ticket_message", ""),
            "general_answer": local_answer or "",
            "memory_answer": local_answer or "",
            "memory_update": state.get("memory_update", {}),
            "conversation_history": state.get("short_term_history", []),
            "user_memory": state.get("user_memory", {}),
            # Internal server closure used only to construct authenticated
            # memory tools. It is intentionally omitted by _compact_context.
            "_memory_runtime": state.get("memory_runtime"),
            "citations": state.get("rag_citations", []),
            "sources": state.get("sql_sources", []),
            "sql_status": sql_output.sql_status if sql_output is not None else None,
        }
        writer = _safe_stream_writer()
        if route in {"rag", "ticket_guidance"} and rag_result_count == 0:
            # Do not invoke an LLM with an empty evidence set: it could answer
            # from general knowledge and accidentally imply document grounding.
            no_reference_answer = (
                NO_APPROVED_TICKET_GUIDANCE_MESSAGE
                if route == "ticket_guidance"
                else NO_REFERENCE_MESSAGE
            )
            no_reference_reason = (
                "NO_APPROVED_TICKET_GUIDANCE_REFERENCE"
                if route == "ticket_guidance"
                else "NO_SUFFICIENTLY_RELEVANT_REFERENCE"
            )
            composition = AnswerComposition(
                answer=no_reference_answer,
                backend="deterministic_no_reference",
                fallback_reason=no_reference_reason,
            )
            writer({"type": "response.delta", "delta": composition.answer})
        else:
            composition = compose_with_streaming(
                composer,
                context,
                lambda delta: writer({"type": "response.delta", "delta": delta}),
                lambda message: writer(
                    {
                        "type": "response.error",
                        "reason_code": "ANSWER_PROVIDER_FALLBACK",
                        "message": message,
                        "recoverable": True,
                    }
                ),
            )
        next_state: OrchestratorState = {
            **state,
            "final_answer": composition.answer,
            "composer_backend": composition.backend,
            "general_answer": local_answer or "",
            "general_answer_available": bool(local_answer),
            "memory_tool_calls": list(composition.tool_calls),
            "memory_tool_outcomes": list(composition.tool_outcomes),
        }
        if composition.tool_calls:
            next_state["trace"] = append_trace(
                next_state,
                "memory_tools",
                {
                    "status": "called",
                    "tools": list(composition.tool_calls),
                },
            )
        if route == "GENERAL_KNOWLEDGE" and composition.backend.startswith("openai"):
            next_state["general_answer_available"] = True
        if composition.error:
            next_state["composer_error"] = composition.error
        if composition.fallback_reason:
            next_state["composer_fallback_reason"] = composition.fallback_reason
        next_state["trace"] = append_trace(
            next_state,
            "compose_final_answer",
            {
                "status": "no_reference" if route in {"rag", "ticket_guidance"} and rag_result_count == 0 else "composed",
                "backend": composition.backend,
                "error": composition.error,
                "fallback_reason": composition.fallback_reason,
                "answer_chars": len(composition.answer),
                "reference_status": reference_status,
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

        response.update(_intent_response_fields(state))
        if state.get("composer_fallback_reason"):
            response["model_fallback_reason"] = state["composer_fallback_reason"]
        if state.get("sql_output") is not None:
            response["sql_planner_backend"] = state.get("sql_planner_backend", "deterministic")
            response["sql_planner_fallback_reason"] = state.get("sql_planner_fallback_reason")
        if state.get("memory_tool_calls"):
            response["memory_tools"] = {
                "called": list(dict.fromkeys(state["memory_tool_calls"]))[:4],
                "outcomes": list(dict.fromkeys(state.get("memory_tool_outcomes", [])))[:4],
                "server_identity": "authenticated_runtime",
            }

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
            **_reference_response_fields(state),
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
            "ticket_preview": state.get("ticket_preview"),
            "approval_required": bool(state.get("ticket_approval_required", False)),
            "missing_fields": state.get("missing_fields", []),
            "profile": profile.to_public_dict(),
            "latency_ms": _elapsed_ms(started_at),
            **_turn_context(state),
        }

    if route == "CASUAL":
        return {
            "status": "answered",
            "reason_code": "CASUAL",
            "route": route,
            "model_backend": "deterministic",
            "category": category,
            "message": state.get("casual_message", "Hi! How can I help you today?"),
            "sql_execution": {"status": "not_run", "row_count": 0},
            "profile": profile.to_public_dict(),
            "latency_ms": _elapsed_ms(started_at),
            **_turn_context(state),
        }

    if route == "GENERAL_KNOWLEDGE":
        answered = bool(state.get("general_answer_available", False))
        return {
            "status": "answered" if answered else "no_answer",
            "reason_code": "GENERAL_KNOWLEDGE" if answered else "GENERAL_KNOWLEDGE_UNAVAILABLE",
            "route": route,
            "model_backend": state.get("composer_backend"),
            "category": category,
            "message": state.get("final_answer", ""),
            "sql_execution": {"status": "not_run", "row_count": 0},
            "profile": profile.to_public_dict(),
            "latency_ms": _elapsed_ms(started_at),
            **_turn_context(state),
        }

    if route == "memory":
        memory_message = state.get("final_answer") or state.get("memory_answer", "")
        answered = bool(memory_message) and not str(memory_message).startswith("I do not have that detail")
        return {
            "status": "answered" if answered else "no_answer",
            "reason_code": "LONG_TERM_MEMORY" if answered else "LONG_TERM_MEMORY_EMPTY",
            "route": route,
            "model_backend": state.get("composer_backend", "none"),
            "category": category,
            "message": memory_message,
            "sql_execution": {"status": "not_run", "row_count": 0},
            "profile": profile.to_public_dict(),
            "latency_ms": _elapsed_ms(started_at),
            **_turn_context(state),
        }

    if route == "ticket_guidance":
        answered = int(state.get("rag_result_count", 0)) > 0
        return {
            "status": "answered" if answered else "no_answer",
            "reason_code": "TICKET_GUIDANCE_FROM_KB" if answered else "NO_APPROVED_TICKET_GUIDANCE_REFERENCE",
            "route": route,
            "model_backend": state.get("composer_backend"),
            "category": category,
            "message": final_answer or state.get("rag_message", NO_APPROVED_TICKET_GUIDANCE_MESSAGE),
            "citations": state.get("rag_citations", []),
            "profile": profile.to_public_dict(),
            "latency_ms": _elapsed_ms(started_at),
            **_reference_response_fields(state),
            **_turn_context(state),
        }

    if route in {"feedback", "clarification", "unsupported"}:
        if route == "feedback":
            message = state.get("feedback_message", "")
            status = "answered"
            reason_code = state.get("reason_code", "FEEDBACK_GUIDANCE")
        elif route == "unsupported" and state.get("intent") == "history_lookup":
            message = state.get("history_message", state.get("unsupported_message", ""))
            status = state.get("status", "no_answer")
            reason_code = state.get("reason_code", "SHORT_TERM_MEMORY_EMPTY")
        elif route == "clarification":
            message = state.get("clarification_message", "")
            status = state.get("status", "needs_clarification")
            reason_code = state.get("reason_code", "INTENT_NEEDS_CLARIFICATION")
        else:
            message = state.get("unsupported_message", "")
            status = "unsupported"
            reason_code = state.get("reason_code", "UNSUPPORTED_REQUEST")
        return {
            "status": status,
            "reason_code": reason_code,
            "route": route,
            "model_backend": "none",
            "category": category,
            "message": message,
            "sql_execution": {"status": "not_run", "row_count": 0},
            "profile": profile.to_public_dict(),
            "latency_ms": _elapsed_ms(started_at),
            **_turn_context(state),
        }

    has_results = int(state.get("rag_result_count", 0)) > 0
    return {
        "status": "answered" if has_results else "no_answer",
        "reason_code": "ANSWERED_FROM_GRAPH_RAG" if has_results else "NO_SUFFICIENTLY_RELEVANT_REFERENCE",
        "route": route,
        "model_backend": state.get("composer_backend"),
        "sql_execution": {"status": "not_run", "row_count": 0},
        "category": category,
        "message": final_answer or state.get("rag_message", ""),
        "citations": state.get("rag_citations", []),
        "profile": profile.to_public_dict(),
        "latency_ms": _elapsed_ms(started_at),
        **_reference_response_fields(state),
        **_turn_context(state),
    }


def _intent_response_fields(state: OrchestratorState) -> dict[str, Any]:
    """Add the public versioned classifier contract without raw model data."""

    result = state.get("intent_result")
    if result is None:
        return {
            "intent": state.get("intent"),
            "intent_confidence": state.get("intent_confidence"),
            "needs_clarification": bool(state.get("needs_clarification", False)),
            "clarification_question": state.get("clarification_question") or None,
            "missing_context": list(state.get("missing_context", [])),
            "intent_contract_version": "nexusone-intent-contract-v1",
            "intent_classifier_version": state.get("classifier_version"),
        }
    return {
        "intent": state.get("intent"),
        "intent_confidence": state.get("intent_confidence"),
        "needs_clarification": bool(state.get("needs_clarification", False)),
        "clarification_question": state.get("clarification_question") or None,
        "missing_context": list(state.get("missing_context", [])),
        "intent_contract_version": getattr(result, "contract_version", "nexusone-intent-contract-v1"),
        "intent_classifier_version": state.get("classifier_version"),
    }


def _memory_lookup_answer(state: OrchestratorState) -> str | None:
    """Answer only exact bounded profile-memory questions from sanitized data."""

    message = str(state.get("clean_message", "")).casefold()
    memory = state.get("user_memory", {})
    if not isinstance(memory, dict):
        return None
    field_labels = {
        "nickname": ("nickname", "preferred name"),
        "name": ("full name", "your name", "my name"),
        "profession": ("profession", "job", "occupation"),
        "working_timezone": ("working timezone", "timezone"),
        "office_location": ("office location",),
        "language": ("preferred language", "language"),
        "response_style": ("response style",),
        "date_format": ("date format",),
        "communication_channel": ("communication channel",),
        "current_activities": ("current activit", "working on"),
    }
    if not (
        message.startswith("what is my ")
        or message.startswith("what's my ")
        or message.startswith("do you remember my ")
        or message.startswith("what am i working on")
    ):
        return None
    for field, labels in field_labels.items():
        if not any(label in message for label in labels):
            continue
        if field == "profession":
            value = memory.get("profession")
            if isinstance(value, str) and value:
                return f"You asked me to remember that your profession is {value}."
        elif field == "current_activities":
            values = memory.get("current_activities")
            if isinstance(values, list) and values:
                return "You asked me to remember that you are currently working on " + ", ".join(values) + "."
        else:
            groups = ("name_and_nickname", "preferences", "other_facts", "facts")
            for group in groups:
                values = memory.get(group)
                candidate = "preferred_name" if field == "nickname" and group == "facts" else field
                if isinstance(values, dict) and isinstance(values.get(candidate), str) and values[candidate]:
                    label = "nickname" if field == "nickname" else field.replace("_", " ")
                    return f"You asked me to remember that your {label} is {values[candidate]}."
        return "I do not have that detail in your saved profile memory."
    return None


def _classification_context(state: OrchestratorState) -> dict[str, Any]:
    """Pass bounded, explicitly untrusted context to classification only."""

    context = state.get("conversation_context")
    result: dict[str, Any] = dict(context) if isinstance(context, dict) else {}
    history = state.get("short_term_history", [])
    if history:
        result["recent_user_messages"] = [
            item.get("user_message", "")[:300]
            for item in history[-3:]
            if isinstance(item, dict) and item.get("user_message")
        ]
    memory = state.get("user_memory", {})
    if isinstance(memory, dict):
        result["user_memory"] = memory
    return result


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
    if route == "CASUAL":
        return "answered"
    if route == "GENERAL_KNOWLEDGE":
        return "answered" if state.get("general_answer_available") else "no_answer"
    if route == "memory":
        return "answered" if state.get("memory_answer") else "no_answer"
    if route == "ticket_guidance":
        return "answered" if int(state.get("rag_result_count", 0)) > 0 else "no_answer"
    return "answered" if int(state.get("rag_result_count", 0)) > 0 else "no_answer"


def _reference_response_fields(state: OrchestratorState) -> dict[str, Any]:
    status = state.get("rag_reference_status", "not_used")
    if status == "not_used":
        return {"reference_status": "not_used"}
    return {
        "reference_status": status,
        "source_similarity_threshold": state.get("rag_threshold"),
    }


def _turn_context(state: OrchestratorState) -> dict[str, str]:
    return {
        "conversation_id": str(state.get("conversation_id", "web-chat")),
        "turn_id": str(state.get("turn_id", "web-turn")),
    }


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _safe_stream_writer() -> Any:
    try:
        return get_stream_writer()
    except RuntimeError:
        return lambda _event: None


def _chunk_source_refs(
    results: tuple[ChunkSearchResult, ...],
    *,
    threshold: float = SOURCE_SIMILARITY_THRESHOLD,
    sanitize_source_text: bool = False,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    retained = tuple(result for result in results if result.score >= threshold)
    for index, result in enumerate(retained, start=1):
        payload = result.chunk.citation.to_dict()
        payload.update(
            {
                "reference_id": index,
                "label": f"[{index}]",
                "chunk_id": result.chunk.chunk_id,
                "chunk_index": result.chunk.chunk_index,
                "excerpt": result.snippet,
                "text": (
                    sanitize_ticket_guidance_source_text(result.chunk.text)
                    if sanitize_source_text
                    else result.chunk.text
                ),
                "score": result.score,
                "lexical_score": result.lexical_score,
                "semantic_score": result.semantic_score,
            }
        )
        refs.append(payload)
    return refs


def _local_source_refs(
    results: tuple[RetrievalResult, ...],
    *,
    threshold: float = SOURCE_SIMILARITY_THRESHOLD,
    sanitize_source_text: bool = False,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    retained = tuple(result for result in results if result.score >= threshold)
    for index, result in enumerate(retained, start=1):
        payload = result.document.citation.to_dict()
        payload.update(
            {
                "reference_id": index,
                "label": f"[{index}]",
                "excerpt": result.snippet,
                "text": (
                    sanitize_ticket_guidance_source_text(result.document.body)
                    if sanitize_source_text
                    else result.document.body
                ),
                "score": result.score,
                "lexical_score": result.score,
                "semantic_score": 0.0,
            }
        )
        refs.append(payload)
    return refs


def _bounded_source_metadata(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return trace-safe metadata without source text or grant metadata."""

    return [
        {
            key: source[key]
            for key in (
                "reference_id",
                "doc_id",
                "title",
                "source_type",
                "source_path",
                "score",
                "lexical_score",
                "semantic_score",
            )
            if key in source
        }
        for source in citations[:20]
    ]
