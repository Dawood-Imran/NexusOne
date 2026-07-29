"""LangGraph wiring for the NexusOne main orchestrator."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Mapping

from langgraph.graph import END, START, StateGraph

from app.actions.ticket_service import TicketService
from app.agents.orchestrator.answer_composer import AnswerComposer, build_default_answer_composer
from app.agents.orchestrator.intent_classifier import IntentClassifier, build_default_intent_classifier
from app.agents.orchestrator.nodes import (
    make_compose_final_answer_node,
    make_finalize_response_node,
    make_load_user_context_node,
    make_precheck_guardrails_node,
    make_recheck_guardrails_node,
    make_retrieve_rag_node,
    make_respond_casual_node,
    make_respond_clarification_node,
    make_respond_feedback_node,
    make_respond_unsupported_node,
    make_route_question_node,
    make_run_ticket_action_node,
    make_run_sql_node,
    make_validate_answer_node,
)
from app.agents.orchestrator.state import OrchestratorRun, OrchestratorState
from app.agents.sql_subgraph.planner import build_default_sql_planner
from app.agents.sql_subgraph.state import SQLExecutor, SQLPlanner
from app.observability.langsmith import build_langsmith_config
from app.retrieval.chunk_index import MetadataChunkRetriever
from app.retrieval.local_kb import LocalKBRetriever


def build_orchestrator_graph(
    *,
    chunk_retriever: MetadataChunkRetriever | None = None,
    local_retriever: LocalKBRetriever | None = None,
    sql_executor: SQLExecutor | None = None,
    sql_planner: SQLPlanner | None = None,
    answer_composer: AnswerComposer | None = None,
    intent_classifier: IntentClassifier | None = None,
    ticket_service: TicketService | None = None,
) -> Any:
    """Build the main graph.

    The graph owns orchestration only. Permission checks, retrieval, and SQL
    validation remain in their dedicated modules.
    """

    graph = StateGraph(OrchestratorState)
    graph.add_node("load_user_context", make_load_user_context_node())
    graph.add_node("precheck_guardrails", make_precheck_guardrails_node())
    graph.add_node(
        "route_question",
        make_route_question_node(intent_classifier or build_default_intent_classifier()),
    )
    graph.add_node("recheck_guardrails", make_recheck_guardrails_node())
    graph.add_node("respond_casual", make_respond_casual_node())
    graph.add_node("respond_feedback", make_respond_feedback_node())
    graph.add_node("respond_clarification", make_respond_clarification_node())
    graph.add_node("respond_unsupported", make_respond_unsupported_node())
    graph.add_node("run_ticket_action", make_run_ticket_action_node(ticket_service))
    graph.add_node(
        "run_sql_subgraph",
        make_run_sql_node(sql_executor, sql_planner if sql_planner is not None else build_default_sql_planner()),
    )
    graph.add_node("retrieve_rag_context", make_retrieve_rag_node(chunk_retriever, local_retriever))
    graph.add_node("validate_answer", make_validate_answer_node())
    composer = answer_composer or build_default_answer_composer()
    graph.add_node("compose_final_answer", make_compose_final_answer_node(composer))
    graph.add_node("compose_general_knowledge", make_compose_final_answer_node(composer))
    graph.add_node("finalize_response", make_finalize_response_node())

    graph.add_edge(START, "load_user_context")
    graph.add_edge("load_user_context", "precheck_guardrails")
    graph.add_edge("precheck_guardrails", "route_question")
    graph.add_edge("route_question", "recheck_guardrails")
    graph.add_conditional_edges(
        "recheck_guardrails",
        _route_after_question,
        {
            "deny": "finalize_response",
            "error": "finalize_response",
            "sql": "run_sql_subgraph",
            "rag": "retrieve_rag_context",
            "ticket_guidance": "retrieve_rag_context",
            "combined": "run_sql_subgraph",
            "ticket_create": "run_ticket_action",
            "CASUAL": "respond_casual",
            "GENERAL_KNOWLEDGE": "compose_general_knowledge",
            "feedback": "respond_feedback",
            "clarification": "respond_clarification",
            "unsupported": "respond_unsupported",
        },
    )
    graph.add_conditional_edges(
        "run_sql_subgraph",
        _route_after_sql,
        {
            "combined": "retrieve_rag_context",
            "validate": "validate_answer",
        },
    )
    graph.add_edge("run_ticket_action", "validate_answer")
    graph.add_edge("respond_casual", "validate_answer")
    graph.add_edge("respond_feedback", "validate_answer")
    graph.add_edge("respond_clarification", "validate_answer")
    graph.add_edge("respond_unsupported", "validate_answer")
    graph.add_edge("retrieve_rag_context", "validate_answer")
    graph.add_conditional_edges(
        "validate_answer",
        _route_after_validation,
        {
            "casual": "finalize_response",
            "general_knowledge": "finalize_response",
            "direct": "finalize_response",
            "compose": "compose_final_answer",
        },
    )
    graph.add_edge("compose_general_knowledge", "validate_answer")
    graph.add_edge("compose_final_answer", "finalize_response")
    graph.add_edge("finalize_response", END)
    return graph.compile()


class NexusOneOrchestrator:
    """Invoke-style wrapper around the compiled LangGraph orchestrator."""

    def __init__(
        self,
        *,
        chunk_retriever: MetadataChunkRetriever | None = None,
        local_retriever: LocalKBRetriever | None = None,
        sql_executor: SQLExecutor | None = None,
        sql_planner: SQLPlanner | None = None,
        answer_composer: AnswerComposer | None = None,
        intent_classifier: IntentClassifier | None = None,
        ticket_service: TicketService | None = None,
    ) -> None:
        self.graph = build_orchestrator_graph(
            chunk_retriever=chunk_retriever,
            local_retriever=local_retriever,
            sql_executor=sql_executor,
            sql_planner=sql_planner,
            answer_composer=answer_composer,
            intent_classifier=intent_classifier,
            ticket_service=ticket_service,
        )

    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.invoke_with_trace(payload).response

    def invoke_with_trace(self, payload: Mapping[str, Any]) -> OrchestratorRun:
        state = _state_from_payload(payload)
        output = self.graph.invoke(state, config=build_langsmith_config(state))
        response = output["response"]
        trace = tuple(output.get("trace", ()))
        return OrchestratorRun(response=response, trace=trace)

    def stream_with_events(self, payload: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
        """Stream safe answer events from the existing graph execution.

        LangGraph remains the source of orchestration truth.  Only the
        composer emits custom delta events; graph state and prompts are never
        forwarded to the HTTP client.  The final event carries the same
        response mapping returned by :meth:`invoke`.
        """

        state = _state_from_payload(payload)
        final_response: Mapping[str, Any] | None = None
        for event in self.graph.stream(
            state,
            config=build_langsmith_config(state),
            stream_mode=["updates", "custom"],
            version="v2",
        ):
            if not isinstance(event, Mapping):
                continue
            event_type = event.get("type")
            if event_type == "custom":
                data = event.get("data")
                if isinstance(data, Mapping) and data.get("type") in {"response.delta", "response.error"}:
                    yield dict(data)
                continue
            if event_type != "updates":
                continue
            data = event.get("data")
            if not isinstance(data, Mapping):
                continue
            for node_update in data.values():
                if isinstance(node_update, Mapping) and isinstance(node_update.get("response"), Mapping):
                    final_response = node_update["response"]

        if final_response is None:
            raise RuntimeError("graph did not produce a final response")
        yield {"type": "response.complete", "response": dict(final_response)}


def _state_from_payload(payload: Mapping[str, Any]) -> OrchestratorState:
    state: OrchestratorState = {
        "conversation_id": str(payload.get("conversation_id", "web-chat")),
        "turn_id": str(payload.get("turn_id", "web-turn")),
        "user_id": str(payload.get("user_id", "")),
        "message": payload.get("message") if isinstance(payload.get("message"), str) else "",
        "include_trace": bool(payload.get("include_trace", False)),
        "execute_sql": bool(payload.get("execute_sql", False)),
        "conversation_context": payload.get("conversation_context"),
        "active_ticket_draft": payload.get("active_ticket_draft"),
        "short_term_history": _bounded_short_term_history(payload.get("short_term_history")),
        "user_memory": _bounded_user_memory(payload.get("user_memory")),
    }
    # Authenticated API callers may pass the immutable server-resolved profile
    # so the graph does not reconstruct identity from client data.
    if payload.get("profile") is not None:
        state["profile"] = payload["profile"]
    return state


def _bounded_short_term_history(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list | tuple):
        return []
    history: list[dict[str, str]] = []
    for item in value[-8:]:
        if not isinstance(item, Mapping):
            continue
        user_message = item.get("user_message")
        assistant_message = item.get("assistant_message")
        if not isinstance(user_message, str):
            continue
        history.append(
            {
                "user_message": user_message.strip()[:600],
                "assistant_message": assistant_message.strip()[:600] if isinstance(assistant_message, str) else "",
            }
        )
    return history


def _bounded_user_memory(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"schema_version": 1, "facts": {}, "preferences": {}}
    result: dict[str, Any] = {"schema_version": 1, "facts": {}, "preferences": {}}
    for group in ("facts", "preferences"):
        source = value.get(group)
        if not isinstance(source, Mapping):
            continue
        result[group] = {
            str(field)[:48]: str(item)[:120]
            for field, item in list(source.items())[:8]
            if isinstance(field, str) and isinstance(item, str) and item.strip()
        }
    return result


def _route_after_question(state: OrchestratorState) -> str:
    return state.get("route", "error")


def _route_after_sql(state: OrchestratorState) -> str:
    return "combined" if state.get("route") == "combined" else "validate"


def _route_after_validation(state: OrchestratorState) -> str:
    route = state.get("route")
    if route == "CASUAL":
        return "casual"
    if route == "GENERAL_KNOWLEDGE":
        return "general_knowledge"
    if route in {"feedback", "clarification", "unsupported"}:
        return "direct"
    return "compose"
