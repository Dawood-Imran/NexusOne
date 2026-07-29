"""Server-controlled ticket workflow and permission-safe repositories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import re
import secrets
from threading import Lock
from typing import Any, Mapping, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.auth.profiles import UserProfile, get_profile


ALLOWED_DEPARTMENTS = {"it", "hr", "admin"}
ALLOWED_PRIORITIES = {"low", "normal", "high", "urgent"}
DEFAULT_VISIBILITY_SCOPE = "own"
ALLOWED_CREATION_VISIBILITY_SCOPES = {DEFAULT_VISIBILITY_SCOPE}
ELIGIBLE_CLOSE_STATUSES = {"open", "in_progress", "waiting_on_user", "resolved"}
QUEUE_POLICIES = {
    "it": ("it_admin", "it_team"),
    "hr": ("hr", "hr_team"),
    "admin": ("admin_ops", "admin_ops_team"),
    "finance": ("finance", "finance_team"),
}
CLOSE_ROLES = {"it_admin", "hr", "admin_ops"}
# Synthetic queue routing is server-owned. A creator can choose only the
# allowlisted department; they cannot choose an assignee or widen visibility.
QUEUE_ROUTING_ASSIGNEES = {"it": "u005", "hr": "u003", "admin": "u008"}
TICKET_ID_PATTERN = re.compile(r"^[A-Z]{2,5}-[0-9]{3,8}$")


@dataclass(frozen=True)
class TicketRequest:
    department: str | None
    category: str | None
    priority: str | None
    description: str | None
    visibility_scope: str = DEFAULT_VISIBILITY_SCOPE
    # ``comment`` is accepted as an input alias, but persistence always uses
    # the validated ``description`` field. It is never an identity selector.
    comment: str | None = None


@dataclass(frozen=True)
class TicketCreationResult:
    status: str
    message: str
    ticket: Mapping[str, Any] | None = None
    ticket_preview: Mapping[str, Any] | None = None
    missing_fields: tuple[str, ...] = ()
    reason_code: str | None = None
    approval_id: str | None = None


class TicketNotFoundError(Exception):
    """A ticket is not visible to the authenticated caller."""


class TicketRepository(Protocol):
    def create_ticket(self, profile: UserProfile, request: TicketRequest) -> Mapping[str, Any]:
        """Persist a ticket and its created event, returning a sanitized row."""

    def list_tickets(self, profile: UserProfile) -> tuple[Mapping[str, Any], ...]: ...

    def get_ticket(self, profile: UserProfile, ticket_id: str) -> Mapping[str, Any] | None: ...

    def add_comment(self, profile: UserProfile, ticket_id: str, comment: str) -> Mapping[str, Any] | None: ...

    def close_ticket(self, profile: UserProfile, ticket_id: str, comment: str) -> Mapping[str, Any] | None: ...


@dataclass(frozen=True)
class _PendingTicket:
    approval_id: str
    request: TicketRequest
    preview: Mapping[str, Any]


class TicketService:
    """Validate, preview, approve, and authorize ticket actions on the server.

    A preview is held against the authenticated ``(user_id, conversation_id)``
    pair. The browser may display or repeat the opaque approval id, but it can
    never choose the creator, queue visibility, or persisted ticket fields.
    """

    def __init__(self, repository: TicketRepository | None = None) -> None:
        self.repository = repository or InMemoryTicketRepository()
        self._lock = Lock()
        self._drafts: dict[tuple[str, str], TicketRequest] = {}
        self._pending: dict[tuple[str, str], _PendingTicket] = {}
        self._completed: dict[tuple[str, str], Mapping[str, Any]] = {}
        self._denied: set[tuple[str, str]] = set()

    def create_ticket(self, profile: UserProfile | None, request: TicketRequest) -> TicketCreationResult:
        """Compatibility entry point that now always creates a preview.

        Final persistence is only reachable through :meth:`approve_ticket`.
        """

        return self.preview_ticket(profile, request)

    def preview_ticket(
        self,
        profile: UserProfile | None,
        request: TicketRequest,
        *,
        conversation_id: str = "web-chat",
    ) -> TicketCreationResult:
        if profile is None:
            return _unknown_user_result()
        if profile.status != "active":
            return _inactive_user_result()

        key = _workflow_key(profile, conversation_id)
        normalized = normalize_ticket_request(request)
        with self._lock:
            prior = self._pending.get(key)
            prior_request = prior.request if prior is not None else self._drafts.get(key)
            normalized = merge_ticket_requests(prior_request, normalized)
            validation = _validate_ticket_request(normalized)
            if validation is not None:
                self._drafts[key] = normalized
                self._pending.pop(key, None)
                return validation

            approval_id = secrets.token_urlsafe(24)
            preview = build_ticket_preview(profile, normalized)
            self._drafts.pop(key, None)
            self._pending[key] = _PendingTicket(approval_id, normalized, preview)
            self._completed.pop(key, None)
            self._denied.discard(key)
            return TicketCreationResult(
                status="needs_approval",
                reason_code="TICKET_PREVIEW_READY",
                message=format_ticket_preview_message(preview),
                ticket_preview=preview,
                approval_id=approval_id,
            )

    def approve_ticket(
        self,
        profile: UserProfile | None,
        *,
        conversation_id: str = "web-chat",
        approval_id: str | None = None,
    ) -> TicketCreationResult:
        if profile is None:
            return _unknown_user_result()
        if profile.status != "active":
            return _inactive_user_result()

        key = _workflow_key(profile, conversation_id)
        with self._lock:
            completed = self._completed.get(key)
            if completed is not None:
                return TicketCreationResult(
                    status="denied",
                    reason_code="TICKET_ALREADY_APPROVED",
                    message="That ticket preview was already approved; no duplicate ticket was created.",
                    ticket=completed,
                )
            pending = self._pending.get(key)
            if pending is None:
                return TicketCreationResult(
                    status="needs_approval",
                    reason_code="TICKET_APPROVAL_REQUIRED",
                    message="There is no pending ticket preview to approve. Provide the team, category, priority, and non-empty details first.",
                )
            if approval_id is not None and approval_id != pending.approval_id:
                return TicketCreationResult(
                    status="denied",
                    reason_code="TICKET_APPROVAL_INVALID",
                    message="That ticket approval is no longer valid. Review the current ticket preview and approve it explicitly.",
                )

            ticket = dict(self.repository.create_ticket(profile, pending.request))
            self._pending.pop(key, None)
            self._drafts.pop(key, None)
            self._completed[key] = ticket
            return TicketCreationResult(
                status="ticket_created",
                reason_code="TICKET_CREATED",
                message=format_ticket_created_message(ticket),
                ticket=ticket,
                approval_id=pending.approval_id,
            )

    def deny_ticket(
        self,
        profile: UserProfile | None,
        *,
        conversation_id: str = "web-chat",
    ) -> TicketCreationResult:
        if profile is None:
            return _unknown_user_result()
        key = _workflow_key(profile, conversation_id)
        with self._lock:
            if key not in self._pending:
                if key in self._completed:
                    return TicketCreationResult(
                        status="denied",
                        reason_code="TICKET_ALREADY_APPROVED",
                        message="That ticket was already approved and cannot be canceled from this preview.",
                        ticket=self._completed[key],
                    )
                return TicketCreationResult(
                    status="not_created",
                    reason_code="TICKET_APPROVAL_NOT_FOUND",
                    message="There is no pending ticket preview to cancel.",
                )
            self._pending.pop(key, None)
            self._drafts.pop(key, None)
            self._denied.add(key)
            return TicketCreationResult(
                status="not_created",
                reason_code="TICKET_APPROVAL_DENIED",
                message="The ticket was not created. No support record was saved.",
            )

    def workflow_signal(self, profile: UserProfile | None, conversation_id: str, message: str) -> str | None:
        """Resolve approval/edit intent from server-held state, not a model."""

        if profile is None:
            return None
        key = _workflow_key(profile, conversation_id)
        with self._lock:
            has_pending = key in self._pending
            has_draft = key in self._drafts
        if not has_pending and not has_draft:
            return None
        lowered = " ".join(str(message).strip().casefold().split())
        if _is_approval_message(lowered):
            return "approve"
        if _is_denial_message(lowered):
            return "deny"
        return "edit" if has_pending else "create"

    def list_tickets(self, profile: UserProfile | None) -> tuple[Mapping[str, Any], ...]:
        if profile is None or profile.status != "active":
            return ()
        return tuple(self.repository.list_tickets(profile))

    def get_ticket(self, profile: UserProfile | None, ticket_id: str) -> Mapping[str, Any] | None:
        if profile is None or profile.status != "active" or not _valid_ticket_id(ticket_id):
            return None
        return self.repository.get_ticket(profile, ticket_id.upper())

    def add_comment(
        self,
        profile: UserProfile | None,
        ticket_id: str,
        comment: str | None,
    ) -> TicketCreationResult:
        if profile is None:
            return _unknown_user_result()
        if profile.status != "active":
            return _inactive_user_result()
        normalized_id = _normalize_ticket_id(ticket_id)
        normalized_comment = normalize_comment(comment)
        if normalized_id is None:
            return _ticket_not_found_result()
        if normalized_comment is None:
            return TicketCreationResult(
                status="needs_clarification",
                reason_code="TICKET_COMMENT_REQUIRED",
                message="Please provide a non-empty comment or details before adding it to the ticket.",
            )
        result = self.repository.add_comment(profile, normalized_id, normalized_comment)
        if result is None:
            return _ticket_not_found_result()
        return TicketCreationResult(
            status="comment_added",
            reason_code="TICKET_COMMENT_ADDED",
            message="Your comment was added to the ticket.",
            ticket=result,
        )

    def close_ticket(
        self,
        profile: UserProfile | None,
        ticket_id: str,
        comment: str | None,
    ) -> TicketCreationResult:
        if profile is None:
            return _unknown_user_result()
        if profile.status != "active":
            return _inactive_user_result()
        normalized_id = _normalize_ticket_id(ticket_id)
        normalized_comment = normalize_comment(comment)
        if normalized_id is None:
            return _ticket_not_found_result()
        if normalized_comment is None:
            return TicketCreationResult(
                status="needs_clarification",
                reason_code="TICKET_COMMENT_REQUIRED",
                message="Please provide a non-empty closing comment or details explaining the resolution.",
            )
        if profile.role not in CLOSE_ROLES:
            return TicketCreationResult(
                status="denied",
                reason_code="TICKET_CLOSE_NOT_AUTHORIZED",
                message="Only authorized HR, IT, or Admin support personnel can close this ticket.",
            )
        result = self.repository.close_ticket(profile, normalized_id, normalized_comment)
        if result is None:
            return TicketCreationResult(
                status="denied",
                reason_code="TICKET_CLOSE_NOT_AUTHORIZED",
                message="You are not authorized to close that ticket, or it is no longer eligible for closure.",
            )
        return TicketCreationResult(
            status="ticket_closed",
            reason_code="TICKET_CLOSED",
            message=f"Ticket {result.get('ticket_id')} is now closed.",
            ticket=result,
        )


class InMemoryTicketRepository:
    """Process-local repository used by deterministic tests and local demos."""

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
        visibility_scope = require_creation_visibility_scope(request.visibility_scope)
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
                "assigned_to": QUEUE_ROUTING_ASSIGNEES.get(department),
                "created_at": now,
                "updated_at": now,
                "description": description,
                "visibility_scope": visibility_scope,
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
        return sanitize_ticket(raw_ticket, requester_name=profile.name)

    def list_tickets(self, profile: UserProfile) -> tuple[Mapping[str, Any], ...]:

        with self._lock:
            return tuple(
                sanitize_ticket(ticket, requester_name=_requester_display_name(ticket, profile))
                for ticket in self.tickets
                if can_access_ticket(profile, ticket)
            )

    def get_ticket(self, profile: UserProfile, ticket_id: str) -> Mapping[str, Any] | None:
        with self._lock:
            ticket = next((item for item in self.tickets if item["ticket_id"] == ticket_id), None)
            if ticket is None or not can_access_ticket(profile, ticket):
                return None
            detail = sanitize_ticket(ticket, requester_name=_requester_display_name(ticket, profile))
            detail["comments"] = [
                {
                    "event_type": event["event_type"],
                    "comment": event["event_text"],
                    "created_at": _public_timestamp(event["created_at"]),
                }
                for event in self.events
                if event["ticket_id"] == ticket_id and event["event_type"] == "comment"
            ]
            return detail

    def add_comment(self, profile: UserProfile, ticket_id: str, comment: str) -> Mapping[str, Any] | None:
        with self._lock:
            ticket = next((item for item in self.tickets if item["ticket_id"] == ticket_id), None)
            if ticket is None or not can_access_ticket(profile, ticket):
                return None
            now = datetime.now(UTC).replace(microsecond=0)
            self.events.append(
                {
                    "ticket_id": ticket_id,
                    "actor_user_id": profile.user_id,
                    "event_type": "comment",
                    "event_text": comment,
                    "created_at": now,
                }
            )
            ticket["updated_at"] = now
            return sanitize_ticket(ticket, requester_name=_requester_display_name(ticket, profile))

    def close_ticket(self, profile: UserProfile, ticket_id: str, comment: str) -> Mapping[str, Any] | None:
        with self._lock:
            ticket = next((item for item in self.tickets if item["ticket_id"] == ticket_id), None)
            if (
                ticket is None
                or not can_access_ticket(profile, ticket)
                or profile.role not in CLOSE_ROLES
                or ticket.get("status") not in ELIGIBLE_CLOSE_STATUSES
            ):
                return None
            now = datetime.now(UTC).replace(microsecond=0)
            ticket["status"] = "closed"
            ticket["updated_at"] = now
            self.events.append(
                {
                    "ticket_id": ticket_id,
                    "actor_user_id": profile.user_id,
                    "event_type": "status_changed",
                    "event_text": comment,
                    "created_at": now,
                }
            )
            return sanitize_ticket(ticket, requester_name=_requester_display_name(ticket, profile))


class SQLAlchemyTicketRepository:
    """Postgres-backed repository with predicates at every ticket boundary."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create_ticket(self, profile: UserProfile, request: TicketRequest) -> Mapping[str, Any]:
        department = require_value(request.department)
        category = require_value(request.category)
        priority = require_value(request.priority)
        description = require_value(request.description)
        visibility_scope = require_creation_visibility_scope(request.visibility_scope)
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
                {"pattern": f"^{department.upper()}-([0-9]+)$", "regex": f"^{department.upper()}-[0-9]+$"},
            ).scalar_one()
            ticket_id = f"{department.upper()}-{int(next_number)}"
            row = connection.execute(
                text(
                    """
                    INSERT INTO tickets (
                        ticket_id, requester_id, department, category, priority, status,
                        assigned_to, created_at, updated_at, description, visibility_scope
                    )
                    VALUES (
                        :ticket_id, :requester_id, :department, :category, :priority,
                        'open',
                        (
                            SELECT u.user_id
                            FROM users u
                            JOIN user_groups ug ON ug.user_id = u.user_id
                            WHERE u.status = 'active'
                              AND u.department = :department
                              AND (
                                  (:department = 'it' AND u.role = 'it_admin' AND ug.group_name = 'it_team')
                                  OR (:department = 'hr' AND u.role = 'hr' AND ug.group_name = 'hr_team')
                                  OR (:department = 'admin' AND u.role = 'admin_ops' AND ug.group_name = 'admin_ops_team')
                              )
                            ORDER BY u.user_id
                            LIMIT 1
                        ),
                        now(), now(), :description, :visibility_scope
                    )
                    RETURNING ticket_id, requester_id, department, category, priority, status,
                              assigned_to, created_at, updated_at, description, visibility_scope
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
        return sanitize_ticket(dict(row), requester_name=profile.name)

    def list_tickets(self, profile: UserProfile) -> tuple[Mapping[str, Any], ...]:
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT at.ticket_id, at.department, at.category, at.priority, at.status,
                           at.description, at.created_at, at.updated_at, requester.name AS requester_name
                    FROM accessible_tickets(:user_id) at
                    JOIN users requester ON requester.user_id = at.requester_id
                    ORDER BY at.updated_at DESC
                    LIMIT 25
                    """
                ),
                {"user_id": profile.user_id},
            ).mappings().all()
        return tuple(sanitize_ticket(dict(row), requester_name=row.get("requester_name")) for row in rows)

    def get_ticket(self, profile: UserProfile, ticket_id: str) -> Mapping[str, Any] | None:
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT at.ticket_id, at.department, at.category, at.priority, at.status,
                           at.description, at.created_at, at.updated_at, requester.name AS requester_name
                    FROM accessible_tickets(:user_id) at
                    JOIN users requester ON requester.user_id = at.requester_id
                    WHERE at.ticket_id = :ticket_id
                    LIMIT 1
                    """
                ),
                {"user_id": profile.user_id, "ticket_id": ticket_id},
            ).mappings().first()
            if row is None:
                return None
            comments = connection.execute(
                text(
                    """
                    SELECT event_type, event_text, created_at
                    FROM accessible_ticket_events(:user_id)
                    WHERE ticket_id = :ticket_id AND event_type = 'comment'
                    ORDER BY created_at ASC
                    """
                ),
                {"user_id": profile.user_id, "ticket_id": ticket_id},
            ).mappings().all()
        detail = sanitize_ticket(dict(row), requester_name=row.get("requester_name"))
        detail["comments"] = [
            {"event_type": row["event_type"], "comment": row["event_text"], "created_at": _public_timestamp(row["created_at"])}
            for row in comments
        ]
        return detail

    def add_comment(self, profile: UserProfile, ticket_id: str, comment: str) -> Mapping[str, Any] | None:
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    INSERT INTO ticket_events (ticket_id, actor_user_id, event_type, event_text)
                    SELECT :ticket_id, :user_id, 'comment', :comment
                    WHERE can_user_comment_ticket(:user_id, :ticket_id)
                    RETURNING ticket_id
                    """
                ),
                {"ticket_id": ticket_id, "user_id": profile.user_id, "comment": comment},
            ).first()
            if row is None:
                return None
            updated = connection.execute(
                text(
                    """
                    UPDATE tickets
                    SET updated_at = now()
                    WHERE ticket_id = :ticket_id
                      AND can_user_access_ticket(:user_id, ticket_id)
                    RETURNING ticket_id, requester_id, department, category, priority, status, description, created_at, updated_at
                    """
                ),
                {"ticket_id": ticket_id, "user_id": profile.user_id},
            ).mappings().first()
            requester_name = _sql_requester_name(connection, updated) if updated is not None else None
        return sanitize_ticket(dict(updated), requester_name=requester_name) if updated is not None else None

    def close_ticket(self, profile: UserProfile, ticket_id: str, comment: str) -> Mapping[str, Any] | None:
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    UPDATE tickets AS t
                    SET status = 'closed', updated_at = now()
                    WHERE t.ticket_id = :ticket_id
                      AND t.status IN ('open', 'in_progress', 'waiting_on_user', 'resolved')
                      AND can_user_close_ticket(:user_id, t.ticket_id)
                    RETURNING t.ticket_id, t.requester_id, t.department, t.category, t.priority, t.status,
                              t.description, t.created_at, t.updated_at
                    """
                ),
                {"ticket_id": ticket_id, "user_id": profile.user_id},
            ).mappings().first()
            if row is None:
                return None
            requester_name = _sql_requester_name(connection, row)
            connection.execute(
                text(
                    """
                    INSERT INTO ticket_events (ticket_id, actor_user_id, event_type, event_text)
                    VALUES (:ticket_id, :user_id, 'status_changed', :comment)
                    """
                ),
                {"ticket_id": ticket_id, "user_id": profile.user_id, "comment": comment},
            )
        return sanitize_ticket(dict(row), requester_name=requester_name)


def normalize_ticket_request(request: TicketRequest) -> TicketRequest:
    raw_description = request.description if request.description is not None else request.comment
    raw_scope = request.visibility_scope
    normalized_scope = raw_scope.strip().lower() if isinstance(raw_scope, str) and raw_scope.strip() else DEFAULT_VISIBILITY_SCOPE
    return TicketRequest(
        department=_normalize_slug(request.department),
        category=_normalize_slug(request.category),
        priority=_normalize_slug(request.priority) or "normal",
        description=_normalize_description(raw_description),
        visibility_scope=normalized_scope,
    )


def merge_ticket_requests(previous: TicketRequest | None, current: TicketRequest) -> TicketRequest:
    if previous is None:
        return current
    return TicketRequest(
        department=current.department or previous.department,
        category=current.category or previous.category,
        priority=current.priority or previous.priority,
        description=current.description or previous.description,
        visibility_scope=current.visibility_scope or previous.visibility_scope,
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
        "description": "a non-empty comment/details description of what happened or what you need",
    }
    requested = [labels.get(field, field) for field in missing_fields]
    if len(requested) == 1:
        detail = requested[0]
    else:
        detail = ", ".join(requested[:-1]) + f", and {requested[-1]}"
    return f"I can prepare that ticket, but I need these details. Please provide {detail}. I will show you a preview for explicit approval before creating it."


def format_ticket_preview_message(preview: Mapping[str, Any]) -> str:
    return (
        "I have collected the required ticket details. Review this preview: "
        f"{preview.get('department')} / {preview.get('category')}, "
        f"{preview.get('priority')} priority. Details: {preview.get('description')} "
        "Reply ‘Approve ticket’ to create it, or ‘Cancel ticket’ to discard it. "
        "Required information is the team, category, priority, and a non-empty comment/details field."
    )


def format_ticket_created_message(ticket: Mapping[str, Any]) -> str:
    return (
        f"Created ticket {ticket.get('ticket_id')} for {ticket.get('department')} / {ticket.get('category')}. "
        f"Status is {ticket.get('status')} with {ticket.get('priority')} priority."
    )


def build_ticket_preview(profile: UserProfile, request: TicketRequest) -> dict[str, Any]:
    return {
        "requester": profile.name,
        "department": request.department,
        "category": request.category,
        "priority": request.priority,
        "description": request.description,
        "visibility_scope": DEFAULT_VISIBILITY_SCOPE,
    }


def sanitize_ticket(row: Mapping[str, Any], *, requester_name: str | None = None) -> dict[str, Any]:
    """Return authorized ticket fields without raw requester/assignee IDs."""

    result = {
        "ticket_id": row.get("ticket_id"),
        "requester": requester_name,
        "department": row.get("department"),
        "category": row.get("category"),
        "priority": row.get("priority"),
        "status": row.get("status"),
        "description": row.get("description"),
        "created_at": _public_timestamp(row.get("created_at")),
        "updated_at": _public_timestamp(row.get("updated_at")),
    }
    return {key: value for key, value in result.items() if value is not None}


def _requester_display_name(row: Mapping[str, Any], viewer: UserProfile) -> str | None:
    requester_id = row.get("requester_id")
    if requester_id == viewer.user_id:
        return viewer.name
    requester = get_profile(str(requester_id)) if requester_id else None
    return requester.name if requester is not None else None


def _sql_requester_name(connection: Any, row: Mapping[str, Any] | None) -> str | None:
    if not isinstance(row, Mapping) or not row.get("requester_id"):
        return None
    result = connection.execute(
        text("SELECT name FROM users WHERE user_id = :requester_id"),
        {"requester_id": row["requester_id"]},
    ).scalar_one_or_none()
    return str(result) if result else None


def can_access_ticket(profile: UserProfile, row: Mapping[str, Any]) -> bool:
    """Mirror the database predicate for deterministic repositories."""

    if profile.status != "active":
        return False
    if row.get("requester_id") == profile.user_id:
        return True
    if profile.role == "ceo":
        return True
    department = str(row.get("department", ""))
    queue_policy = QUEUE_POLICIES.get(department)
    if queue_policy is not None:
        role, group = queue_policy
        if profile.role == role and profile.department == department and group in profile.groups:
            return row.get("assigned_to") == profile.user_id
    if (
        row.get("visibility_scope") == "manager_team"
        and profile.role == "manager"
        and "managers" in profile.groups
        and row.get("requester_manager_id") == profile.user_id
    ):
        return True
    return False


def normalize_comment(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", value.strip())
    return normalized[:2_000] or None


def require_value(value: str | None) -> str:
    if not value:
        raise ValueError("Ticket request was not validated before persistence.")
    return value


def require_creation_visibility_scope(value: str | None) -> str:
    normalized = value.strip().lower() if isinstance(value, str) and value.strip() else DEFAULT_VISIBILITY_SCOPE
    if normalized not in ALLOWED_CREATION_VISIBILITY_SCOPES:
        raise ValueError("Ticket creation visibility scope is not allowed.")
    return normalized


def _validate_ticket_request(request: TicketRequest) -> TicketCreationResult | None:
    if request.visibility_scope not in ALLOWED_CREATION_VISIBILITY_SCOPES:
        return TicketCreationResult(
            status="denied",
            reason_code="TICKET_SCOPE_NOT_ALLOWED",
            message="New tickets are visible to their creator until an authorized support workflow assigns them.",
        )
    missing = required_missing_fields(request)
    if missing:
        return TicketCreationResult(
            status="needs_clarification",
            reason_code="TICKET_NEEDS_CLARIFICATION",
            missing_fields=missing,
            message=clarification_message(missing),
        )
    if request.department not in ALLOWED_DEPARTMENTS:
        return TicketCreationResult(
            status="denied",
            reason_code="UNSUPPORTED_TICKET_DEPARTMENT",
            message="I can create IT, HR, or Admin tickets right now.",
        )
    if request.priority not in ALLOWED_PRIORITIES:
        return TicketCreationResult(
            status="needs_clarification",
            reason_code="TICKET_NEEDS_CLARIFICATION",
            missing_fields=("priority",),
            message="What priority should I use: low, normal, high, or urgent? I still need a non-empty comment/details field.",
        )
    return None


def _unknown_user_result() -> TicketCreationResult:
    return TicketCreationResult(status="error", reason_code="UNKNOWN_USER", message="The authenticated user could not be found.")


def _inactive_user_result() -> TicketCreationResult:
    return TicketCreationResult(status="denied", reason_code="INACTIVE_USER", message="I cannot create or update tickets for an inactive user profile.")


def _ticket_not_found_result() -> TicketCreationResult:
    return TicketCreationResult(status="denied", reason_code="TICKET_NOT_FOUND_OR_NOT_VISIBLE", message="That ticket is not available to your account.")


def _workflow_key(profile: UserProfile, conversation_id: str) -> tuple[str, str]:
    return profile.user_id, str(conversation_id or "web-chat")[:128]


def _normalize_ticket_id(value: str) -> str | None:
    normalized = str(value or "").strip().upper()
    return normalized if _valid_ticket_id(normalized) else None


def _valid_ticket_id(value: str) -> bool:
    return bool(TICKET_ID_PATTERN.fullmatch(str(value or "").strip().upper()))


def _is_approval_message(message: str) -> bool:
    return message in {"approve", "approve ticket", "confirm", "confirm ticket", "yes approve", "yes create it", "submit ticket"}


def _is_denial_message(message: str) -> bool:
    return message in {"deny", "deny ticket", "cancel", "cancel ticket", "no", "no cancel", "do not create", "don't create"}


def _normalize_slug(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized or None


def _normalize_description(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = re.sub(r"\s+", " ", value.strip())
    # Keep the existing quality floor while making the contract explicit:
    # whitespace and vague one/two-word values are not ticket details.
    if len(normalized.split()) < 4:
        return None
    return normalized[:1_000]


def _public_timestamp(value: Any) -> Any:
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else value
