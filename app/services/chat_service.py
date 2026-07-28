"""Framework-independent chat service for NexusOne Copilot."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Mapping

from sqlalchemy import create_engine

from app.agents.orchestrator.answer_composer import (
    AnswerComposer,
    DeterministicAnswerComposer,
    FallbackAnswerComposer,
    build_default_answer_composer,
)

from app.actions.audit_service import AuditEvent, AuditService, SQLAlchemyAuditRepository
from app.actions.feedback_service import FeedbackService, SQLAlchemyFeedbackRepository
from app.actions.ticket_service import SQLAlchemyTicketRepository, TicketService
from app.agents.orchestrator import NexusOneOrchestrator
from app.agents.sql_subgraph.db import SQLAlchemyExecutor
from app.agents.sql_subgraph.planner import build_default_sql_planner
from app.agents.sql_subgraph.state import SQLExecutor
from app.auth.profiles import list_profiles
from app.auth.service import AuthenticatedSession
from app.retrieval.chunk_index import MetadataChunkRetriever
from app.retrieval.local_kb import LocalKBRetriever
from app.runtime.config import RuntimeConfig, load_dotenv


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
        # ChatService is also used directly by tests and small local scripts.
        # Loading here makes that path follow the same repository .env contract
        # as scripts/run_web_app.py without overriding explicit shell values.
        load_dotenv()
        self.runtime_config = RuntimeConfig.from_env()
        self.retriever = retriever or LocalKBRetriever()
        self.chunk_retriever = chunk_retriever or MetadataChunkRetriever()

        self._database_init_error: str | None = None
        self._database_engine = None
        self.sql_executor = sql_executor
        if self.sql_executor is not None:
            self._database_status = "injected"
        elif self.runtime_config.database_url:
            try:
                self._database_engine = create_engine(self.runtime_config.database_url)
                self.sql_executor = SQLAlchemyExecutor(engine=self._database_engine)
                self._database_status = "configured"
            except Exception as exc:  # noqa: BLE001 - safe startup fallback.
                self._database_status = "unavailable"
                self._database_init_error = type(exc).__name__
        else:
            self._database_status = "not_configured"

        defaults = build_default_action_services(engine=self._database_engine)
        self.ticket_service = ticket_service or defaults["ticket_service"]
        self.feedback_service = feedback_service or defaults["feedback_service"]
        self.audit_service = audit_service or defaults["audit_service"]
        self.sql_planner = sql_planner if sql_planner is not None else build_default_sql_planner()
        self.answer_composer = answer_composer if answer_composer is not None else build_default_answer_composer()
        self.orchestrator = NexusOneOrchestrator(
            chunk_retriever=self.chunk_retriever,
            local_retriever=self.retriever,
            sql_executor=self.sql_executor,
            sql_planner=self.sql_planner,
            answer_composer=self.answer_composer,
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

    def stream_authenticated_message(
        self,
        session: AuthenticatedSession,
        message: str,
        include_trace: bool = False,
    ) -> Iterator[Mapping[str, Any]]:
        """Yield safe delta/error/completion events for an authenticated turn."""

        yield from self.stream_message(
            session.user_id,
            message,
            include_trace=include_trace,
            profile=session.profile,
        )

    def stream_message(
        self,
        user_id: str,
        message: str,
        *,
        include_trace: bool = False,
        profile: Any | None = None,
    ) -> Iterator[Mapping[str, Any]]:
        payload = self._request_payload(user_id, message, include_trace=include_trace, profile=profile)
        for event in self.orchestrator.stream_with_events(payload):
            event_type = event.get("type") if isinstance(event, Mapping) else None
            if event_type == "response.complete":
                raw_response = event.get("response")
                if not isinstance(raw_response, Mapping):
                    raise RuntimeError("stream completion did not include a response")
                response = self._decorate_response(dict(raw_response))
                yield {"type": "response.complete", "response": response}
            elif event_type in {"response.delta", "response.error"}:
                yield dict(event)

    def _handle_message(
        self,
        user_id: str,
        message: str,
        *,
        include_trace: bool,
        profile: Any | None = None,
    ) -> dict[str, Any]:
        payload = self._request_payload(user_id, message, include_trace=include_trace, profile=profile)
        return self._decorate_response(dict(self.orchestrator.invoke(payload)))

    def _request_payload(
        self,
        user_id: str,
        message: str,
        *,
        include_trace: bool,
        profile: Any | None,
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
        return payload

    def _decorate_response(self, response: dict[str, Any]) -> dict[str, Any]:
        response["capabilities"] = self._capabilities_for_response(response)
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
                    model_used=_safe_model_backend(response.get("model_backend")),
                    retrieved_doc_ids=doc_ids,
                    allowed_doc_ids=doc_ids,
                )
            )
        except Exception:
            return

    def _capabilities_for_response(self, response: Mapping[str, Any]) -> dict[str, Any]:
        sql_execution = response.get("sql_execution")
        sql_execution = sql_execution if isinstance(sql_execution, Mapping) else {}
        execution_status = str(sql_execution.get("status", "not_used"))
        if self.sql_executor is None:
            sql_mode = "validation_only"
            sql_status = "unavailable" if self._database_status == "unavailable" else "validation_only"
        else:
            sql_mode = "live"
            sql_status = {
                "executed": "connected",
                "error": "error",
            }.get(execution_status, "configured")

        if response.get("route") == "CASUAL":
            answer_capability = {
                "provider": "deterministic",
                "model": "none",
                "mode": "not_used",
                "fallback_reason": None,
            }
        else:
            answer_capability = _provider_metadata(
                self.answer_composer,
                configured=self.runtime_config.openai_api_key_configured,
                model=self.runtime_config.openai_answer_model,
                unavailable_reason="OPENAI_PROVIDER_UNAVAILABLE",
            )
        if response.get("model_fallback_reason"):
            answer_capability.update(
                {
                    "mode": "fallback",
                    "fallback_reason": str(response["model_fallback_reason"]),
                }
            )
        planner_capability = _provider_metadata(
            self.sql_planner,
            configured=self.runtime_config.openai_api_key_configured,
            model=self.runtime_config.openai_sql_model,
            unavailable_reason="OPENAI_SQL_PLANNER_UNAVAILABLE",
        )
        if response.get("sql_planner_fallback_reason"):
            planner_capability.update(
                {
                    "mode": "fallback",
                    "fallback_reason": str(response["sql_planner_fallback_reason"]),
                }
            )

        return {
            "sql": {
                "mode": sql_mode,
                "status": sql_status,
                "configured": self.runtime_config.database_url is not None or self._database_status == "injected",
                "execution_status": execution_status,
                "row_count": _safe_nonnegative_int(sql_execution.get("row_count", 0)),
            },
            "answer_composer": answer_capability,
            "sql_planner": planner_capability,
            "tracing": {
                "enabled": self.runtime_config.langsmith_tracing,
                "project": self.runtime_config.langsmith_project,
                "api_key_configured": self.runtime_config.langsmith_api_key_configured,
            },
        }


def build_default_action_services(*, database_url: str | None = None, engine: Any | None = None) -> dict[str, Any]:
    """Build persistence services from the configured database when available."""

    if engine is None:
        if database_url is None:
            from app.runtime.config import RuntimeConfig

            database_url = RuntimeConfig.from_env().database_url
        if database_url:
            try:
                engine = create_engine(database_url)
            except Exception:
                engine = None
    if engine is None:
        return {
            "ticket_service": TicketService(),
            "feedback_service": FeedbackService(),
            "audit_service": AuditService(),
        }
    return {
        "ticket_service": TicketService(SQLAlchemyTicketRepository(engine)),
        "feedback_service": FeedbackService(SQLAlchemyFeedbackRepository(engine)),
        "audit_service": AuditService(SQLAlchemyAuditRepository(engine)),
    }


def _provider_metadata(
    component: Any | None,
    *,
    configured: bool,
    model: str,
    unavailable_reason: str,
) -> dict[str, Any]:
    """Describe provider selection without exposing credentials or prompts."""

    if component is None:
        return {
            "provider": "deterministic",
            "model": model,
            "mode": "fallback",
            "fallback_reason": "OPENAI_API_KEY_NOT_CONFIGURED" if not configured else unavailable_reason,
        }

    if isinstance(component, FallbackAnswerComposer):
        primary = component.primary
        provider = str(getattr(primary, "provider_name", "openai"))
        selected_model = str(getattr(primary, "model_name", model))
        return {
            "provider": provider,
            "model": selected_model,
            "mode": "configured_with_fallback",
            "fallback_reason": None,
        }

    provider = str(getattr(component, "provider_name", ""))
    if not provider:
        provider = "deterministic" if isinstance(component, DeterministicAnswerComposer) else "custom"
    selected_model = str(getattr(component, "model_name", model)) if provider == "openai" else model
    fallback_reason = getattr(component, "fallback_reason", None)
    if provider == "deterministic" and fallback_reason is None:
        fallback_reason = "OPENAI_API_KEY_NOT_CONFIGURED" if not configured else unavailable_reason
    return {
        "provider": provider,
        "model": selected_model,
        "mode": "fallback" if provider == "deterministic" else "configured",
        "fallback_reason": fallback_reason,
    }


def _safe_model_backend(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= 100 and "\n" not in text else None


def _safe_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0
