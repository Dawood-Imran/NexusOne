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
from app.agents.orchestrator.intent_classifier import IntentClassifier, build_default_intent_classifier

from app.actions.audit_service import AuditEvent, AuditService, SQLAlchemyAuditRepository
from app.actions.feedback_service import FeedbackService, SQLAlchemyFeedbackRepository
from app.actions.ticket_service import SQLAlchemyTicketRepository, TicketService
from app.agents.orchestrator import NexusOneOrchestrator
from app.agents.sql_subgraph.db import SQLAlchemyExecutor
from app.agents.sql_subgraph.planner import build_default_sql_planner
from app.agents.sql_subgraph.state import SQLExecutor
from app.auth.profiles import get_profile, list_profiles
from app.auth.service import AuthenticatedSession
from app.guardrails.policy import check_message_access
from app.memory.conversation_store import ConversationStore, SQLiteConversationStore, TurnReservation
from app.memory.extraction import extract_explicit_memory_update
from app.memory.tools import MemoryRuntimeContext, UserMemoryTools
from app.memory.user_memory import JSONUserMemoryStore, MemoryValidationError, UserMemoryStore
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
        intent_classifier: IntentClassifier | None = None,
        ticket_service: TicketService | None = None,
        feedback_service: FeedbackService | None = None,
        audit_service: AuditService | None = None,
        conversation_store: ConversationStore | None = None,
        user_memory_store: UserMemoryStore | None = None,
    ) -> None:
        # ChatService is also used directly by tests and small local scripts.
        # Loading here makes that path follow the same repository .env contract
        # as scripts/run_web_app.py without overriding explicit shell values.
        load_dotenv()
        self.runtime_config = RuntimeConfig.from_env()
        self.conversation_store = conversation_store or SQLiteConversationStore(
            self.runtime_config.conversation_database_path
        )
        self.user_memory_store = user_memory_store or JSONUserMemoryStore(self.runtime_config.user_memory_dir)
        self.memory_tools = UserMemoryTools(self.user_memory_store)
        self.retriever = retriever or LocalKBRetriever(
            similarity_threshold=self.runtime_config.retrieval_config.source_similarity_threshold
        )
        self.chunk_retriever = chunk_retriever or MetadataChunkRetriever(config=self.runtime_config.retrieval_config)

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
        self.intent_classifier = intent_classifier if intent_classifier is not None else build_default_intent_classifier()
        self.orchestrator = NexusOneOrchestrator(
            chunk_retriever=self.chunk_retriever,
            local_retriever=self.retriever,
            sql_executor=self.sql_executor,
            sql_planner=self.sql_planner,
            answer_composer=self.answer_composer,
            intent_classifier=self.intent_classifier,
            ticket_service=self.ticket_service,
        )

    def profiles(self) -> list[dict[str, object]]:
        return list_profiles()

    def handle_message(
        self,
        user_id: str,
        message: str,
        include_trace: bool = False,
        *,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        conversation_context: Any = None,
        active_ticket_draft: Any = None,
        memory_opt_in: bool = False,
    ) -> dict[str, Any]:
        """Handle a trusted graph/unit call, optionally using durable memory.

        Legacy direct callers that omit ``conversation_id`` retain the old
        ``web-chat``/``web-turn`` shape. Authenticated HTTP callers always pass
        through the durable conversation path.
        """

        return self._handle_message(
            user_id,
            message,
            include_trace=include_trace,
            profile=None,
            conversation_id=conversation_id,
            turn_id=turn_id,
            persist_memory=conversation_id is not None or turn_id is not None,
            conversation_context=conversation_context,
            active_ticket_draft=active_ticket_draft,
            memory_opt_in=memory_opt_in,
        )

    def handle_authenticated_message(
        self,
        session: AuthenticatedSession,
        message: str,
        include_trace: bool = False,
        *,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        conversation_context: Any = None,
        active_ticket_draft: Any = None,
        memory_opt_in: bool = False,
    ) -> dict[str, Any]:
        """Handle chat using only the immutable session identity."""

        return self._handle_message(
            session.user_id,
            message,
            include_trace=include_trace,
            profile=session.profile,
            conversation_id=conversation_id,
            turn_id=turn_id,
            persist_memory=True,
            conversation_context=conversation_context,
            active_ticket_draft=active_ticket_draft,
            memory_opt_in=memory_opt_in,
        )

    def stream_authenticated_message(
        self,
        session: AuthenticatedSession,
        message: str,
        include_trace: bool = False,
        *,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        conversation_context: Any = None,
        active_ticket_draft: Any = None,
        memory_opt_in: bool = False,
    ) -> Iterator[Mapping[str, Any]]:
        """Yield safe events for a durable authenticated turn."""

        yield from self.stream_message(
            session.user_id,
            message,
            include_trace=include_trace,
            profile=session.profile,
            conversation_id=conversation_id,
            turn_id=turn_id,
            persist_memory=True,
            conversation_context=conversation_context,
            active_ticket_draft=active_ticket_draft,
            memory_opt_in=memory_opt_in,
        )

    def stream_message(
        self,
        user_id: str,
        message: str,
        *,
        include_trace: bool = False,
        profile: Any | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        persist_memory: bool = False,
        conversation_context: Any = None,
        active_ticket_draft: Any = None,
        memory_opt_in: bool = False,
    ) -> Iterator[Mapping[str, Any]]:
        payload, reservation, memory_update = self._prepare_request(
            user_id,
            message,
            profile=profile,
            include_trace=include_trace,
            conversation_id=conversation_id,
            turn_id=turn_id,
            persist_memory=persist_memory,
            conversation_context=conversation_context,
            active_ticket_draft=active_ticket_draft,
            memory_opt_in=memory_opt_in,
        )
        if reservation.is_replay:
            yield {"type": "response.start", "conversation_id": reservation.conversation_id, "turn_id": reservation.turn_id}
            yield {"type": "response.complete", "response": dict(reservation.replay_response or {})}
            return

        yield {"type": "response.start", "conversation_id": reservation.conversation_id, "turn_id": reservation.turn_id}
        try:
            for event in self.orchestrator.stream_with_events(payload):
                event_type = event.get("type") if isinstance(event, Mapping) else None
                if event_type == "response.complete":
                    raw_response = event.get("response")
                    if not isinstance(raw_response, Mapping):
                        raise RuntimeError("stream completion did not include a response")
                    response = self._decorate_response(dict(raw_response), memory_update=memory_update)
                    if persist_memory:
                        self.conversation_store.complete_turn(
                            user_id, reservation.conversation_id, reservation.turn_id, response
                        )
                    yield {"type": "response.complete", "response": response}
                elif event_type in {"response.delta", "response.error"}:
                    yield dict(event)
        except Exception:
            response = self._decorate_response(
                {
                    "status": "error",
                    "reason_code": "ORCHESTRATOR_ERROR",
                    "route": "error",
                    "message": "We could not complete that request. Try again in a moment.",
                    "conversation_id": reservation.conversation_id,
                    "turn_id": reservation.turn_id,
                },
                memory_update=memory_update,
            )
            if persist_memory:
                self.conversation_store.complete_turn(
                    user_id, reservation.conversation_id, reservation.turn_id, response
                )
            yield {
                "type": "response.error",
                "reason_code": "STREAM_ERROR",
                "message": response["message"],
                "recoverable": False,
            }
            yield {"type": "response.complete", "response": response}

    def _handle_message(
        self,
        user_id: str,
        message: str,
        *,
        include_trace: bool,
        profile: Any | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        persist_memory: bool = False,
        conversation_context: Any = None,
        active_ticket_draft: Any = None,
        memory_opt_in: bool = False,
    ) -> dict[str, Any]:
        payload, reservation, memory_update = self._prepare_request(
            user_id,
            message,
            profile=profile,
            include_trace=include_trace,
            conversation_id=conversation_id,
            turn_id=turn_id,
            persist_memory=persist_memory,
            conversation_context=conversation_context,
            active_ticket_draft=active_ticket_draft,
            memory_opt_in=memory_opt_in,
        )
        if reservation.is_replay:
            return dict(reservation.replay_response or {})
        try:
            response = self._decorate_response(
                dict(self.orchestrator.invoke(payload)), memory_update=memory_update
            )
        except Exception:
            response = self._decorate_response(
                {
                    "status": "error",
                    "reason_code": "ORCHESTRATOR_ERROR",
                    "route": "error",
                    "message": "We could not complete that request. Try again in a moment.",
                    "conversation_id": reservation.conversation_id,
                    "turn_id": reservation.turn_id,
                },
                memory_update=memory_update,
            )
        if persist_memory:
            self.conversation_store.complete_turn(
                user_id, reservation.conversation_id, reservation.turn_id, response
            )
        return response

    def _prepare_request(
        self,
        user_id: str,
        message: str,
        *,
        profile: Any | None,
        include_trace: bool,
        conversation_id: str | None,
        turn_id: str | None,
        persist_memory: bool,
        conversation_context: Any,
        active_ticket_draft: Any,
        memory_opt_in: bool,
    ) -> tuple[dict[str, Any], TurnReservation, dict[str, Any] | None]:
        if persist_memory:
            reservation = self.conversation_store.begin_turn(user_id, conversation_id, turn_id, message)
        else:
            reservation = TurnReservation(conversation_id or "web-chat", turn_id or "web-turn", ())
        resolved_profile = profile if profile is not None else get_profile(user_id)
        user_memory: dict[str, Any] = {"schema_version": 1, "facts": {}, "preferences": {}}
        if resolved_profile is not None:
            try:
                user_memory = self.memory_tools.get_user_memory(MemoryRuntimeContext(user_id))
            except Exception:
                # Memory is context, never an availability or authorization boundary.
                user_memory = {"schema_version": 1, "facts": {}, "preferences": {}}
        memory_update = self._apply_explicit_memory_update(
            user_id,
            message,
            resolved_profile,
            memory_opt_in=memory_opt_in,
        )
        if memory_update and memory_update.get("status") == "updated":
            try:
                user_memory = self.memory_tools.get_user_memory(MemoryRuntimeContext(user_id))
            except Exception:
                pass
        context = dict(conversation_context) if isinstance(conversation_context, Mapping) else {}
        if reservation.history:
            context["recent_user_messages"] = [item["user_message"] for item in reservation.history[-3:]]
        payload = self._request_payload(
            user_id,
            message,
            include_trace=include_trace,
            profile=resolved_profile,
            conversation_id=reservation.conversation_id,
            turn_id=reservation.turn_id,
            conversation_context=context,
            active_ticket_draft=active_ticket_draft,
            short_term_history=list(reservation.history),
            user_memory=user_memory,
            memory_update=memory_update,
        )
        return payload, reservation, memory_update

    def _request_payload(
        self,
        user_id: str,
        message: str,
        *,
        include_trace: bool,
        profile: Any | None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        conversation_context: Any = None,
        active_ticket_draft: Any = None,
        short_term_history: list[dict[str, str]] | None = None,
        user_memory: dict[str, Any] | None = None,
        memory_update: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "conversation_id": conversation_id or "web-chat",
            "turn_id": turn_id or "web-turn",
            "user_id": user_id,
            "message": message,
            "include_trace": include_trace,
            "execute_sql": self.sql_executor is not None,
            "conversation_context": conversation_context,
            "active_ticket_draft": active_ticket_draft,
            "short_term_history": short_term_history or [],
            "user_memory": user_memory or {"schema_version": 1, "facts": {}, "preferences": {}},
        }
        if memory_update:
            payload["memory_update"] = memory_update
        if profile is not None:
            payload["profile"] = profile
        return payload

    def _decorate_response(
        self,
        response: dict[str, Any],
        *,
        memory_update: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if memory_update:
            response["memory"] = dict(memory_update)
        response["capabilities"] = self._capabilities_for_response(response)
        self._record_audit(response)
        return response

    def _apply_explicit_memory_update(
        self,
        user_id: str,
        message: str,
        profile: Any | None,
        *,
        memory_opt_in: bool,
    ) -> dict[str, Any] | None:
        candidate = extract_explicit_memory_update(message, preference_opt_in=memory_opt_in)
        if candidate is None:
            return None
        if profile is None:
            return {"status": "not_updated", "reason_code": "UNKNOWN_USER", "fields": []}
        decision = check_message_access(profile, message)
        if not decision.allowed:
            return {"status": "not_updated", "reason_code": "ACCESS_DENIED", "fields": []}
        try:
            self.memory_tools.update_user_memory(
                MemoryRuntimeContext(
                    user_id,
                    preference_opt_in=candidate.preference_opt_in or memory_opt_in,
                    explicit_user_input=True,
                ),
                {"facts": candidate.facts, "preferences": candidate.preferences},
            )
        except MemoryValidationError:
            return {"status": "not_updated", "reason_code": "MEMORY_VALUE_REJECTED", "fields": []}
        return {
            "status": "updated",
            "reason_code": "EXPLICIT_USER_MEMORY",
            "fields": list(candidate.fields)[:8],
        }

    def create_authenticated_conversation(self, session: AuthenticatedSession) -> dict[str, Any]:
        return self.conversation_store.create_conversation(session.user_id).to_public_dict(include_turns=False)

    def list_authenticated_conversations(self, session: AuthenticatedSession) -> list[dict[str, Any]]:
        return [
            conversation.to_public_dict(include_turns=True)
            for conversation in self.conversation_store.list_conversations(session.user_id)
        ]

    def get_authenticated_conversation(
        self,
        session: AuthenticatedSession,
        conversation_id: str,
    ) -> dict[str, Any]:
        return self.conversation_store.get_conversation(session.user_id, conversation_id).to_public_dict(include_turns=True)

    def delete_authenticated_conversation(self, session: AuthenticatedSession, conversation_id: str) -> None:
        self.conversation_store.delete_conversation(session.user_id, conversation_id)

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
                    # Audit intent/route metadata must reflect the graph route,
                    # not the terminal reason code (for example, ticket_guidance
                    # must not be recorded as GENERAL_KNOWLEDGE).
                    route=response.get("route"),
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
        classifier_capability = _classifier_metadata(self.intent_classifier)
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
            "intent_classifier": classifier_capability,
            "sql_planner": planner_capability,
            "retrieval": self.chunk_retriever.safe_metadata(),
            "memory": {
                "short_term": "sqlite_local",
                "long_term": "json_profile_local",
                "history_turn_limit": 8,
            },
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


def _classifier_metadata(component: Any | None) -> dict[str, Any]:
    """Return classifier capability metadata without prompt or secret values."""

    if component is None:
        return {
            "provider": "unavailable",
            "model": "none",
            "mode": "safe_failure",
            "reason_code": "INTENT_CLASSIFIER_UNAVAILABLE",
        }
    safe_metadata = getattr(component, "safe_metadata", None)
    if callable(safe_metadata):
        metadata = safe_metadata()
        if isinstance(metadata, Mapping):
            return {str(key): value for key, value in metadata.items()}
    return {
        "provider": str(getattr(component, "provider_name", "custom")),
        "model": str(getattr(component, "model_name", "unknown")),
        "mode": "injected",
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
