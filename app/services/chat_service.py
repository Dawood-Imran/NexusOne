"""Framework-independent chat service for NexusOne Copilot."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine

from app.actions.audit_service import AuditEvent, AuditService, SQLAlchemyAuditRepository
from app.actions.feedback_service import FeedbackService, SQLAlchemyFeedbackRepository
from app.actions.ticket_service import SQLAlchemyTicketRepository, TicketService
from app.agents.orchestrator import NexusOneOrchestrator
from app.agents.orchestrator.answer_composer import AnswerComposer
from app.agents.sql_subgraph.state import SQLExecutor
from app.auth.profiles import list_profiles
from app.auth.service import AuthenticatedSession
from app.retrieval.chunk_index import MetadataChunkRetriever
from app.retrieval.local_kb import LocalKBRetriever


class ChatService:
    """Web/API facade over the main LangGraph orchestrator."""

    def __init__(
        self,
        retriever: LocalKBRetriever | None = None,
        chunk_retriever: MetadataChunkRetriever | None = None,
        sql_executor: SQLExecutor | None = None,
        sql_planner: Any | None = None,
        answer_composer: AnswerComposer | None = None,
        ticket_service: TicketService | None = None,
        feedback_service: FeedbackService | None = None,
        audit_service: AuditService | None = None,
    ) -> None:
        self.retriever = retriever or LocalKBRetriever()
        self.chunk_retriever = chunk_retriever or MetadataChunkRetriever()
        self.sql_executor = sql_executor
        defaults = build_default_action_services()
        self.ticket_service = ticket_service or defaults["ticket_service"]
        self.feedback_service = feedback_service or defaults["feedback_service"]
        self.audit_service = audit_service or defaults["audit_service"]
        self.orchestrator = NexusOneOrchestrator(
            chunk_retriever=self.chunk_retriever,
            local_retriever=self.retriever,
            sql_executor=sql_executor,
            sql_planner=sql_planner,
            answer_composer=answer_composer,
            ticket_service=self.ticket_service,
        )

    def profiles(self) -> list[dict[str, object]]:
        return list_profiles()

    def handle_message(self, user_id: str, message: str, include_trace: bool = False) -> dict[str, Any]:
        """Handle a message for a trusted server-side identity.

        The development HTTP adapter must call
        :meth:`handle_authenticated_message`; this lower-level method remains
        available for graph/unit callers that already resolved identity.
        """

        return self._handle_message(user_id, message, include_trace=include_trace)

    def handle_authenticated_message(
        self,
        session: AuthenticatedSession,
        message: str,
        include_trace: bool = False,
    ) -> dict[str, Any]:
        """Handle chat using only the immutable identity resolved by auth."""

        return self._handle_message(
            session.user_id,
            message,
            include_trace=include_trace,
            profile=session.profile,
        )

    def _handle_message(
        self,
        user_id: str,
        message: str,
        *,
        include_trace: bool,
        profile: Any | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "conversation_id": "web-chat",
            "turn_id": "web-turn",
            "user_id": user_id,
            "message": message,
            "include_trace": include_trace,
            "execute_sql": self.sql_executor is not None,
        }
        if profile is not None:
            payload["profile"] = profile
        response = dict(self.orchestrator.invoke(payload))
        self._record_audit(response)
        return response

    def submit_authenticated_feedback(
        self,
        session: AuthenticatedSession,
        *,
        conversation_id: str,
        turn_id: str,
        rating: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Persist feedback under the session identity, not client input."""

        return self.submit_feedback(
            conversation_id=conversation_id,
            turn_id=turn_id,
            user_id=session.user_id,
            rating=rating,
            comment=comment,
        )

    def submit_feedback(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        user_id: str | None,
        rating: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        result = self.feedback_service.submit_feedback(
            conversation_id=conversation_id,
            turn_id=turn_id,
            user_id=user_id,
            rating=rating,
            comment=comment,
        )
        return {
            "status": result.status,
            "reason_code": result.reason_code,
            "feedback_id": result.feedback_id,
            "message": result.message,
        }

    def _record_audit(self, response: dict[str, Any]) -> None:
        profile = response.get("profile") or {}
        trace = response.get("trace") or []
        tools_called = tuple(
            step.get("node")
            for step in trace
            if isinstance(step, dict) and step.get("node") in {"retrieve_rag_context", "run_sql_subgraph", "run_ticket_action"}
        )
        citations = response.get("citations") or []
        doc_ids = tuple(
            str(citation.get("doc_id"))
            for citation in citations
            if isinstance(citation, dict) and citation.get("doc_id")
        )
        try:
            self.audit_service.record_chat_turn(
                AuditEvent(
                    conversation_id=str(response.get("conversation_id", "web-chat")),
                    turn_id=str(response.get("turn_id", "web-turn")),
                    user_id=str(profile.get("user_id")) if profile.get("user_id") else None,
                    role=str(profile.get("role")) if profile.get("role") else None,
                    route=response.get("reason_code"),
                    category=response.get("category"),
                    tools_called=tools_called,
                    final_answer_status=str(response.get("status", "error")),
                    latency_ms=response.get("latency_ms") if isinstance(response.get("latency_ms"), int) else None,
                    retrieved_doc_ids=doc_ids,
                    allowed_doc_ids=doc_ids,
                )
            )
        except Exception:
            return


def build_default_action_services() -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return {
            "ticket_service": TicketService(),
            "feedback_service": FeedbackService(),
            "audit_service": AuditService(),
        }
    engine = create_engine(database_url)
    return {
        "ticket_service": TicketService(SQLAlchemyTicketRepository(engine)),
        "feedback_service": FeedbackService(SQLAlchemyFeedbackRepository(engine)),
        "audit_service": AuditService(SQLAlchemyAuditRepository(engine)),
    }
