"""Deterministic ticket creation service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
from threading import Lock
from typing import Any, Mapping, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.auth.profiles import UserProfile


ALLOWED_DEPARTMENTS = {"it", "hr", "admin"}
ALLOWED_PRIORITIES = {"low", "normal", "high", "urgent"}
DEFAULT_VISIBILITY_SCOPE = "own"


@dataclass(frozen=True)
class TicketRequest:
    department: str | None
    category: str | None
    priority: str | None
    description: str | None
    visibility_scope: str = DEFAULT_VISIBILITY_SCOPE


@dataclass(frozen=True)
class TicketCreationResult:
    status: str
    message: str
    ticket: Mapping[str, Any] | None = None
    missing_fields: tuple[str, ...] = ()
    reason_code: str | None = None


class TicketRepository(Protocol):
    def create_ticket(self, profile: UserProfile, request: TicketRequest) -> Mapping[str, Any]:
        """Persist a ticket and its created event, returning a sanitized row."""


class TicketService:
    """Validate and create support tickets without exposing hidden DB fields."""

    def __init__(self, repository: TicketRepository | None = None) -> None:
        self.repository = repository or InMemoryTicketRepository()

    def create_ticket(self, profile: UserProfile | None, request: TicketRequest) -> TicketCreationResult:
        if profile is None:
            return TicketCreationResult(
                status="error",
                reason_code="UNKNOWN_USER",
                message="The selected demo user could not be found.",
            )
        if profile.status != "active":
            return TicketCreationResult(
                status="denied",
                reason_code="INACTIVE_USER",
                message="I cannot create tickets for an inactive user profile.",
            )

        normalized = normalize_ticket_request(request)
        missing = required_missing_fields(normalized)
        if missing:
            return TicketCreationResult(
                status="needs_clarification",
                reason_code="TICKET_NEEDS_CLARIFICATION",
                missing_fields=missing,
                message=clarification_message(missing),
            )

        if normalized.department not in ALLOWED_DEPARTMENTS:
            return TicketCreationResult(
                status="denied",
                reason_code="UNSUPPORTED_TICKET_DEPARTMENT",
                message="I can create IT, HR, or Admin tickets right now.",
            )
        if normalized.priority not in ALLOWED_PRIORITIES:
            return TicketCreationResult(
                status="needs_clarification",
                reason_code="TICKET_NEEDS_CLARIFICATION",
                missing_fields=("priority",),
                message="What priority should I use: low, normal, high, or urgent?",
            )

        ticket = dict(self.repository.create_ticket(profile, normalized))
        return TicketCreationResult(
            status="ticket_created",
            reason_code="TICKET_CREATED",
            ticket=ticket,
            message=format_ticket_created_message(ticket),
        )


class InMemoryTicketRepository:
    """Small process-local repository for unit tests and no-DB demos."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._counters = {"it": 5000, "hr": 5000, "admin": 5000}
        self.tickets: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    def create_ticket(self, profile: UserProfile, request: TicketRequest) -> Mapping[str, Any]:
        department = require_value(request.department)
        category = require_value(request.category)
        priority = require_value(request.priority)
        description = require_value(request.description)
        with self._lock:
            self._counters[department] += 1
            ticket_id = f"{department.upper()}-{self._counters[department]}"
            now = datetime.now(UTC).replace(microsecond=0)
            raw_ticket = {
                "ticket_id": ticket_id,
                "requester_id": profile.user_id,
                "department": department,
                "category": category,
                "priority": priority,
                "status": "open",
                "assigned_to": None,
                "created_at": now,
                "updated_at": now,
                "description": description,
                "visibility_scope": request.visibility_scope or DEFAULT_VISIBILITY_SCOPE,
            }
            self.tickets.append(raw_ticket)
            self.events.append(
                {
                    "ticket_id": ticket_id,
                    "actor_user_id": profile.user_id,
                    "event_type": "created",
                    "event_text": "Ticket created by NexusOne Copilot.",
                    "created_at": now,
                }
            )
        return sanitize_ticket(raw_ticket)


class SQLAlchemyTicketRepository:
    """Postgres-backed repository for the local Docker database."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create_ticket(self, profile: UserProfile, request: TicketRequest) -> Mapping[str, Any]:
        department = require_value(request.department)
        category = require_value(request.category)
        priority = require_value(request.priority)
        description = require_value(request.description)
        visibility_scope = request.visibility_scope or DEFAULT_VISIBILITY_SCOPE
        with self.engine.begin() as connection:
            next_number = connection.execute(
                text(
                    """
                    SELECT COALESCE(
                        MAX((regexp_match(ticket_id, :pattern))[1]::integer),
                        5000
                    ) + 1 AS next_number
                    FROM tickets
                    WHERE ticket_id ~ :regex
                    """
                ),
                {
                    "pattern": f"^{department.upper()}-([0-9]+)$",
                    "regex": f"^{department.upper()}-[0-9]+$",
                },
            ).scalar_one()
            ticket_id = f"{department.upper()}-{int(next_number)}"
            row = connection.execute(
                text(
                    """
                    INSERT INTO tickets (
                        ticket_id,
                        requester_id,
                        department,
                        category,
                        priority,
                        status,
                        assigned_to,
                        created_at,
                        updated_at,
                        description,
                        visibility_scope
                    )
                    VALUES (
                        :ticket_id,
                        :requester_id,
                        :department,
                        :category,
                        :priority,
                        'open',
                        NULL,
                        now(),
                        now(),
                        :description,
                        :visibility_scope
                    )
                    RETURNING ticket_id, department, category, priority, status, created_at, updated_at
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "requester_id": profile.user_id,
                    "department": department,
                    "category": category,
                    "priority": priority,
                    "description": description,
                    "visibility_scope": visibility_scope,
                },
            ).mappings().one()
            connection.execute(
                text(
                    """
                    INSERT INTO ticket_events (ticket_id, actor_user_id, event_type, event_text)
                    VALUES (:ticket_id, :actor_user_id, 'created', :event_text)
                    """
                ),
                {
                    "ticket_id": ticket_id,
                    "actor_user_id": profile.user_id,
                    "event_text": "Ticket created by NexusOne Copilot.",
                },
            )
        return sanitize_ticket(dict(row))


def normalize_ticket_request(request: TicketRequest) -> TicketRequest:
    return TicketRequest(
        department=_normalize_slug(request.department),
        category=_normalize_slug(request.category),
        priority=_normalize_slug(request.priority) or "normal",
        description=_normalize_description(request.description),
        visibility_scope=request.visibility_scope or DEFAULT_VISIBILITY_SCOPE,
    )


def required_missing_fields(request: TicketRequest) -> tuple[str, ...]:
    missing = []
    if not request.department:
        missing.append("department")
    if not request.category:
        missing.append("category")
    if not request.description:
        missing.append("description")
    return tuple(missing)


def clarification_message(missing_fields: tuple[str, ...]) -> str:
    labels = {
        "department": "which team should handle it: IT, HR, or Admin",
        "category": "what category fits the request",
        "description": "a short description of what happened or what you need",
    }
    requested = [labels.get(field, field) for field in missing_fields]
    if len(requested) == 1:
        detail = requested[0]
    else:
        detail = ", ".join(requested[:-1]) + f", and {requested[-1]}"
    return f"I can create that ticket. Please provide {detail}."


def format_ticket_created_message(ticket: Mapping[str, Any]) -> str:
    return (
        f"Created ticket {ticket.get('ticket_id')} for {ticket.get('department')} / {ticket.get('category')}. "
        f"Status is {ticket.get('status')} with {ticket.get('priority')} priority."
    )


def sanitize_ticket(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ticket_id": row.get("ticket_id"),
        "department": row.get("department"),
        "category": row.get("category"),
        "priority": row.get("priority"),
        "status": row.get("status"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def require_value(value: str | None) -> str:
    if not value:
        raise ValueError("Ticket request was not validated before persistence.")
    return value


def _normalize_slug(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or None


def _normalize_description(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value.strip())
    if len(normalized.split()) < 4:
        return None
    return normalized[:1000]
