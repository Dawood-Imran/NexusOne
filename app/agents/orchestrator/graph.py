"""LangGraph wiring for the NexusOne main orchestrator."""

from __future__ import annotations

from typing import Any, Mapping

from langgraph.graph import END, START, StateGraph

from app.actions.ticket_service import TicketService
from app.agents.orchestrator.answer_composer import AnswerComposer, build_default_answer_composer
from app.agents.orchestrator.nodes import (
    make_compose_final_answer_node,
    make_finalize_response_node,
    make_load_user_context_node,
    make_precheck_guardrails_node,
    make_retrieve_rag_node,
    make_route_question_node,
    make_run_ticket_action_node,
    make_run_sql_node,
    make_validate_answer_node,
)
from app.agents.orchestrator.state import OrchestratorRun, OrchestratorState
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
    ticket_service: TicketService | None = None,
) -> Any:
    """Build the main graph.

    The graph owns orchestration only. Permission checks, retrieval, and SQL
    validation remain in their dedicated modules.
    """

    graph = StateGraph(OrchestratorState)
    graph.add_node("load_user_context", make_load_user_context_node())
    graph.add_node("precheck_guardrails", make_precheck_guardrails_node())
    graph.add_node("route_question", make_route_question_node())
    graph.add_node("run_ticket_action", make_run_ticket_action_node(ticket_service))
    graph.add_node("run_sql_subgraph", make_run_sql_node(sql_executor, sql_planner))
    graph.add_node("retrieve_rag_context", make_retrieve_rag_node(chunk_retriever, local_retriever))
    graph.add_node("validate_answer", make_validate_answer_node())
    graph.add_node("compose_final_answer", make_compose_final_answer_node(answer_composer or build_default_answer_composer()))
    graph.add_node("finalize_response", make_finalize_response_node())

    graph.add_edge(START, "load_user_context")
    graph.add_edge("load_user_context", "precheck_guardrails")
    graph.add_edge("precheck_guardrails", "route_question")
    graph.add_conditional_edges(
        "route_question",
        _route_after_question,
        {
            "deny": "finalize_response",
            "error": "finalize_response",
            "sql": "run_sql_subgraph",
            "rag": "retrieve_rag_context",
            "combined": "run_sql_subgraph",
            "ticket_create": "run_ticket_action",
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
    graph.add_edge("retrieve_rag_context", "validate_answer")
    graph.add_edge("validate_answer", "compose_final_answer")
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
        ticket_service: TicketService | None = None,
    ) -> None:
        self.graph = build_orchestrator_graph(
            chunk_retriever=chunk_retriever,
            local_retriever=local_retriever,
            sql_executor=sql_executor,
            sql_planner=sql_planner,
            answer_composer=answer_composer,
            ticket_service=ticket_service,
        )

    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return self.invoke_with_trace(payload).response

    def invoke_with_trace(self, payload: Mapping[str, Any]) -> OrchestratorRun:
        state: OrchestratorState = {
            "conversation_id": str(payload.get("conversation_id", "web-chat")),
            "turn_id": str(payload.get("turn_id", "web-turn")),
            "user_id": str(payload.get("user_id", "")),
            "message": str(payload.get("message", "")),
            "include_trace": bool(payload.get("include_trace", False)),
            "execute_sql": bool(payload.get("execute_sql", False)),
        }
        # Authenticated API callers may pass the immutable server-resolved
        # profile so the graph does not reconstruct identity from client data.
        if payload.get("profile") is not None:
            state["profile"] = payload["profile"]
        output = self.graph.invoke(state, config=build_langsmith_config(state))
        response = output["response"]
        trace = tuple(output.get("trace", ()))
        return OrchestratorRun(response=response, trace=trace)


def _route_after_question(state: OrchestratorState) -> str:
    return state.get("route", "error")


def _route_after_sql(state: OrchestratorState) -> str:
    return "combined" if state.get("route") == "combined" else "validate"
