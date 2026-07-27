#!/usr/bin/env python
"""Smoke-test Phase 4 ticket, feedback, and audit writes against Postgres."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.actions.audit_service import AuditEvent, AuditService, SQLAlchemyAuditRepository
from app.actions.feedback_service import FeedbackService, SQLAlchemyFeedbackRepository
from app.actions.ticket_service import SQLAlchemyTicketRepository, TicketRequest, TicketService
from app.auth.profiles import get_profile


DEFAULT_DATABASE_URL = "postgresql+psycopg2://nexusone:nexusone_dev_password@localhost:5492/nexusone"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 4 live Postgres write smoke checks.")
    parser.add_argument("--database-url", default=None, help="SQLAlchemy database URL.")
    parser.add_argument("--user-id", default="u001", help="Demo user id for ticket/feedback/audit writes.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    database_url = args.database_url or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
    engine = create_engine(database_url)
    profile = get_profile(args.user_id)
    if profile is None:
        print(f"Unknown user: {args.user_id}", file=sys.stderr)
        return 2

    ticket_service = TicketService(SQLAlchemyTicketRepository(engine))
    feedback_service = FeedbackService(SQLAlchemyFeedbackRepository(engine))
    audit_service = AuditService(SQLAlchemyAuditRepository(engine))

    ticket_result = ticket_service.create_ticket(
        profile,
        TicketRequest(
            department="it",
            category="cloud_access",
            priority="normal",
            description="Phase 4 smoke test ticket for AWS sandbox access verification.",
        ),
    )
    if ticket_result.status != "ticket_created" or ticket_result.ticket is None:
        print(f"Ticket smoke failed: {ticket_result}", file=sys.stderr)
        return 1
    ticket_id = str(ticket_result.ticket["ticket_id"])

    feedback_result = feedback_service.submit_feedback(
        conversation_id="phase4-smoke",
        turn_id=ticket_id,
        user_id=profile.user_id,
        rating="helpful",
        comment=f"Smoke feedback for {ticket_id}.",
    )
    if feedback_result.status != "stored" or feedback_result.feedback_id is None:
        print(f"Feedback smoke failed: {feedback_result}", file=sys.stderr)
        return 1

    audit_id = audit_service.record_chat_turn(
        AuditEvent(
            conversation_id="phase4-smoke",
            turn_id=ticket_id,
            user_id=profile.user_id,
            role=profile.role,
            route="ticket_create",
            category="own_ticket",
            tools_called=("run_ticket_action",),
            final_answer_status="ticket_created",
            latency_ms=0,
            model_used="deterministic",
        )
    )

    checks = verify_rows(engine, ticket_id, profile.user_id, int(feedback_result.feedback_id), audit_id)
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print(f"Phase 4 smoke failed checks: {', '.join(failed)}", file=sys.stderr)
        return 1

    print("Phase 4 Postgres smoke passed.")
    print(f"ticket_id={ticket_id}")
    print(f"feedback_id={feedback_result.feedback_id}")
    print(f"audit_id={audit_id}")
    return 0


def verify_rows(engine: Any, ticket_id: str, user_id: str, feedback_id: int, audit_id: int) -> dict[str, bool]:
    with engine.connect() as connection:
        ticket_row = connection.execute(
            text("SELECT ticket_id, requester_id, department, status FROM tickets WHERE ticket_id = :ticket_id"),
            {"ticket_id": ticket_id},
        ).mappings().first()
        event_row = connection.execute(
            text("SELECT ticket_id, event_type FROM ticket_events WHERE ticket_id = :ticket_id AND event_type = 'created'"),
            {"ticket_id": ticket_id},
        ).mappings().first()
        feedback_row = connection.execute(
            text("SELECT feedback_id, rating FROM feedback WHERE feedback_id = :feedback_id"),
            {"feedback_id": feedback_id},
        ).mappings().first()
        audit_row = connection.execute(
            text("SELECT audit_id, query, final_answer_status FROM audit_logs WHERE audit_id = :audit_id"),
            {"audit_id": audit_id},
        ).mappings().first()
    return {
        "ticket_inserted": ticket_row is not None and ticket_row["ticket_id"] == ticket_id,
        "ticket_requester_server_side": ticket_row is not None and ticket_row["requester_id"] == user_id,
        "ticket_event_inserted": event_row is not None and event_row["event_type"] == "created",
        "feedback_inserted": feedback_row is not None and feedback_row["rating"] == "helpful",
        "audit_inserted": audit_row is not None and audit_row["query"] == "[redacted]",
        "audit_status_normalized": audit_row is not None and audit_row["final_answer_status"] == "answered",
    }


if __name__ == "__main__":
    raise SystemExit(main())
