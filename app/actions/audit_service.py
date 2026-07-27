"""Safe audit metadata writes for chat turns."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine


SAFE_FINAL_STATUSES = {
    "answered",
    "refused",
    "needs_clarification",
    "error",
}


@dataclass(frozen=True)
class AuditEvent:
    conversation_id: str
    turn_id: str
    user_id: str | None
    role: str | None
    route: str | None
    category: str | None
    tools_called: tuple[str, ...]
    final_answer_status: str
    latency_ms: int | None = None
    model_used: str | None = None
    retrieved_doc_ids: tuple[str, ...] = ()
    allowed_doc_ids: tuple[str, ...] = ()
    denied_doc_count: int = 0


class AuditRepository(Protocol):
    def insert_audit(self, event: AuditEvent) -> int:
        """Persist safe audit metadata and return the audit id."""


class AuditService:
    def __init__(self, repository: AuditRepository | None = None) -> None:
        self.repository = repository or InMemoryAuditRepository()

    def record_chat_turn(self, event: AuditEvent) -> int:
        safe_status = normalize_final_status(event.final_answer_status)
        safe_event = AuditEvent(
            conversation_id=event.conversation_id,
            turn_id=event.turn_id,
            user_id=event.user_id,
            role=event.role,
            route=event.route,
            category=event.category,
            tools_called=tuple(sorted(set(event.tools_called))),
            final_answer_status=safe_status,
            latency_ms=event.latency_ms if event.latency_ms is None or event.latency_ms >= 0 else None,
            model_used=event.model_used,
            retrieved_doc_ids=tuple(event.retrieved_doc_ids),
            allowed_doc_ids=tuple(event.allowed_doc_ids),
            denied_doc_count=max(0, int(event.denied_doc_count)),
        )
        return self.repository.insert_audit(safe_event)


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def insert_audit(self, event: AuditEvent) -> int:
        audit_id = len(self.rows) + 1
        self.rows.append(
            {
                "audit_id": audit_id,
                "conversation_id": event.conversation_id,
                "turn_id": event.turn_id,
                "user_id": event.user_id,
                "role": event.role,
                "query": "[redacted]",
                "intent": event.route,
                "retrieved_doc_ids": list(event.retrieved_doc_ids),
                "allowed_doc_ids": list(event.allowed_doc_ids),
                "denied_doc_count": event.denied_doc_count,
                "tools_called": list(event.tools_called),
                "final_answer_status": event.final_answer_status,
                "model_used": event.model_used,
                "token_usage": {},
                "latency_ms": event.latency_ms,
                "created_at": datetime.now(UTC).replace(microsecond=0),
            }
        )
        return audit_id


class SQLAlchemyAuditRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def insert_audit(self, event: AuditEvent) -> int:
        with self.engine.begin() as connection:
            audit_id = connection.execute(
                text(
                    """
                    INSERT INTO audit_logs (
                        conversation_id,
                        turn_id,
                        user_id,
                        role,
                        query,
                        intent,
                        retrieved_doc_ids,
                        allowed_doc_ids,
                        denied_doc_count,
                        tools_called,
                        final_answer_status,
                        model_used,
                        token_usage,
                        latency_ms
                    )
                    VALUES (
                        :conversation_id,
                        :turn_id,
                        :user_id,
                        :role,
                        '[redacted]',
                        :intent,
                        CAST(:retrieved_doc_ids AS jsonb),
                        CAST(:allowed_doc_ids AS jsonb),
                        :denied_doc_count,
                        CAST(:tools_called AS jsonb),
                        :final_answer_status,
                        :model_used,
                        '{}'::jsonb,
                        :latency_ms
                    )
                    RETURNING audit_id
                    """
                ),
                {
                    "conversation_id": event.conversation_id,
                    "turn_id": event.turn_id,
                    "user_id": event.user_id,
                    "role": event.role,
                    "intent": event.route,
                    "retrieved_doc_ids": _json_array(event.retrieved_doc_ids),
                    "allowed_doc_ids": _json_array(event.allowed_doc_ids),
                    "denied_doc_count": event.denied_doc_count,
                    "tools_called": _json_array(event.tools_called),
                    "final_answer_status": event.final_answer_status,
                    "model_used": event.model_used,
                    "latency_ms": event.latency_ms,
                },
            ).scalar_one()
        return int(audit_id)


def normalize_final_status(status: str) -> str:
    if status in {"denied", "refused"}:
        return "refused"
    if status in {"ticket_created", "validated", "no_answer"}:
        return "answered"
    if status in SAFE_FINAL_STATUSES:
        return status
    return "error"


def _json_array(values: tuple[str, ...]) -> str:
    import json

    return json.dumps(list(values))
