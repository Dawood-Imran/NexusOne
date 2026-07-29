import unittest

from app.actions.ticket_service import (
    InMemoryTicketRepository,
    SQLAlchemyTicketRepository,
    TicketRequest,
    TicketService,
)
from app.auth.profiles import get_profile


class TicketServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryTicketRepository()
        self.service = TicketService(repository=self.repository)
        self.profile = get_profile("u001")
        assert self.profile is not None

    def request(self, *, department: str = "it", category: str = "cloud access") -> TicketRequest:
        return TicketRequest(
            department=department,
            category=category,
            priority="high",
            description="Need access because the billing migration is blocked.",
        )

    def test_complete_request_only_returns_preview_until_explicit_approval(self) -> None:
        preview = self.service.preview_ticket(self.profile, self.request(), conversation_id="conversation-a")

        self.assertEqual("needs_approval", preview.status)
        self.assertEqual("TICKET_PREVIEW_READY", preview.reason_code)
        self.assertIsNotNone(preview.ticket_preview)
        self.assertEqual([], self.repository.tickets)
        self.assertIn("Approve ticket", preview.message)
        self.assertIn("non-empty", preview.message)

        created = self.service.approve_ticket(self.profile, conversation_id="conversation-a", approval_id=preview.approval_id)
        self.assertEqual("ticket_created", created.status)
        self.assertEqual("TICKET_CREATED", created.reason_code)
        self.assertEqual("IT-5001", created.ticket["ticket_id"])
        self.assertEqual("u001", self.repository.tickets[0]["requester_id"])

    def test_approved_ticket_is_server_routed_to_matching_queue_viewer(self) -> None:
        hr_request = TicketRequest(
            department="hr",
            category="payroll",
            priority="normal",
            description="Payroll correction is needed after the employee transfer.",
        )
        preview = self.service.preview_ticket(self.profile, hr_request, conversation_id="hr-route")
        self.service.approve_ticket(self.profile, conversation_id="hr-route", approval_id=preview.approval_id)
        hr = get_profile("u003")
        assert hr is not None

        self.assertEqual({"HR-5001"}, {row["ticket_id"] for row in self.service.list_tickets(hr)})
        self.assertEqual("u003", self.repository.tickets[0]["assigned_to"])

    def test_admin_route_is_visible_only_to_admin_queue_group(self) -> None:
        preview = self.service.preview_ticket(
            self.profile,
            TicketRequest(
                department="admin",
                category="access card",
                priority="normal",
                description="Replacement access card is needed after the badge stopped scanning.",
            ),
            conversation_id="admin-route",
        )
        self.service.approve_ticket(self.profile, conversation_id="admin-route", approval_id=preview.approval_id)
        admin = get_profile("u008")
        finance = get_profile("u004")
        assert admin is not None and finance is not None

        self.assertEqual({"ADMIN-5001"}, {row["ticket_id"] for row in self.service.list_tickets(admin)})
        self.assertNotIn("ADMIN-5001", {row["ticket_id"] for row in self.service.list_tickets(finance)})

    def test_creator_identity_cannot_be_spoofed_by_approval_user(self) -> None:
        other = get_profile("u002")
        assert other is not None
        preview = self.service.preview_ticket(self.profile, self.request(), conversation_id="creator-bound")

        spoofed = self.service.approve_ticket(other, conversation_id="creator-bound", approval_id=preview.approval_id)

        self.assertEqual("needs_approval", spoofed.status)
        self.assertEqual([], self.repository.tickets)
        approved = self.service.approve_ticket(self.profile, conversation_id="creator-bound", approval_id=preview.approval_id)
        self.assertEqual("u001", self.repository.tickets[0]["requester_id"])
        self.assertEqual("ticket_created", approved.status)

    def test_denial_and_duplicate_approval_are_non_writing_and_idempotent(self) -> None:
        preview = self.service.preview_ticket(self.profile, self.request(), conversation_id="approval-state")
        denied = self.service.deny_ticket(self.profile, conversation_id="approval-state")
        self.assertEqual("not_created", denied.status)
        self.assertEqual("TICKET_APPROVAL_DENIED", denied.reason_code)
        self.assertEqual([], self.repository.tickets)

        preview_again = self.service.preview_ticket(self.profile, self.request(), conversation_id="approval-state")
        created = self.service.approve_ticket(self.profile, conversation_id="approval-state", approval_id=preview_again.approval_id)
        duplicate = self.service.approve_ticket(self.profile, conversation_id="approval-state", approval_id=preview_again.approval_id)
        self.assertEqual("ticket_created", created.status)
        self.assertEqual("TICKET_ALREADY_APPROVED", duplicate.reason_code)
        self.assertEqual(1, len(self.repository.tickets))
        self.assertIsNotNone(preview)

    def test_missing_comment_details_are_rejected_and_explicitly_requested(self) -> None:
        result = self.service.preview_ticket(
            self.profile,
            TicketRequest(department="it", category="vpn", priority="normal", description="   "),
            conversation_id="missing-details",
        )

        self.assertEqual("needs_clarification", result.status)
        self.assertIn("description", result.missing_fields)
        self.assertIn("non-empty", result.message)
        self.assertEqual([], self.repository.tickets)

    def test_partial_details_are_completed_from_server_held_draft(self) -> None:
        first = self.service.preview_ticket(
            self.profile,
            TicketRequest(department="it", category=None, priority="normal", description=None),
            conversation_id="draft-state",
        )
        self.assertEqual("needs_clarification", first.status)
        second = self.service.preview_ticket(
            self.profile,
            TicketRequest(department=None, category="vpn", priority="normal", description="VPN access fails after password reset today."),
            conversation_id="draft-state",
        )
        self.assertEqual("needs_approval", second.status)
        self.assertEqual("vpn", second.ticket_preview["category"])
        self.assertEqual([], self.repository.tickets)

    def test_queue_visibility_preserves_creator_and_assignment_scope(self) -> None:
        self.repository.tickets.extend(
            [
                {
                    "ticket_id": "IT-7001", "requester_id": "u001", "department": "it",
                    "category": "vpn", "priority": "normal", "status": "open", "assigned_to": "u005",
                    "created_at": "2026-01-01", "updated_at": "2026-01-01", "description": "x", "visibility_scope": "own",
                },
                {
                    "ticket_id": "HR-7002", "requester_id": "u001", "department": "hr",
                    "category": "payroll", "priority": "normal", "status": "open", "assigned_to": "u003",
                    "created_at": "2026-01-01", "updated_at": "2026-01-01", "description": "x", "visibility_scope": "own",
                },
            ]
        )
        employee = self.service.list_tickets(self.profile)
        it_admin = get_profile("u005")
        hr = get_profile("u003")
        assert it_admin is not None and hr is not None

        self.assertEqual({"IT-7001", "HR-7002"}, {row["ticket_id"] for row in employee})
        self.assertEqual({"IT-7001"}, {row["ticket_id"] for row in self.service.list_tickets(it_admin)})
        self.assertEqual({"HR-7002"}, {row["ticket_id"] for row in self.service.list_tickets(hr)})

    def test_comments_require_text_and_use_same_visibility_predicate(self) -> None:
        preview = self.service.preview_ticket(self.profile, self.request(), conversation_id="comments")
        created = self.service.approve_ticket(self.profile, conversation_id="comments", approval_id=preview.approval_id)
        ticket_id = created.ticket["ticket_id"]
        self.assertEqual("needs_clarification", self.service.add_comment(self.profile, ticket_id, " ").status)
        comment = self.service.add_comment(self.profile, ticket_id, "Additional logs are attached for investigation.")
        self.assertEqual("comment_added", comment.status)
        self.assertEqual(1, len([event for event in self.repository.events if event["event_type"] == "comment"]))

    def test_authorized_close_persists_status_and_unauthorized_close_is_denied(self) -> None:
        preview = self.service.preview_ticket(self.profile, self.request(), conversation_id="close")
        created = self.service.approve_ticket(self.profile, conversation_id="close", approval_id=preview.approval_id)
        ticket_id = created.ticket["ticket_id"]
        it_admin = get_profile("u005")
        assert it_admin is not None
        self.repository.tickets[0]["assigned_to"] = it_admin.user_id

        unauthorized = self.service.close_ticket(self.profile, ticket_id, "Employee cannot close queue ticket.")
        self.assertEqual("TICKET_CLOSE_NOT_AUTHORIZED", unauthorized.reason_code)
        closed = self.service.close_ticket(it_admin, ticket_id, "Resolved after confirming the access policy.")
        self.assertEqual("ticket_closed", closed.status)
        self.assertEqual("closed", self.repository.tickets[0]["status"])
        self.assertEqual("closed", self.service.get_ticket(it_admin, ticket_id)["status"])

    def test_sql_repository_binds_creator_and_injection_like_description(self) -> None:
        engine = _CapturingEngine()
        repository = SQLAlchemyTicketRepository(engine)
        description = "Need VPN access; DROP TABLE tickets; -- after password reset today."

        result = repository.create_ticket(
            self.profile,
            TicketRequest(department="it", category="vpn", priority="normal", description=description),
        )

        self.assertNotIn("requester_id", result)
        self.assertEqual(3, len(engine.connection.calls))
        ticket_query, ticket_params = engine.connection.calls[1]
        self.assertIn(":requester_id", ticket_query)
        self.assertNotIn(description, ticket_query)
        self.assertEqual("u001", ticket_params["requester_id"])
        self.assertEqual(description, ticket_params["description"])
        self.assertIn("requester_id", engine.connection.returned_row)

    def test_unknown_user_cannot_create_ticket(self) -> None:
        result = self.service.preview_ticket(None, self.request(), conversation_id="unknown")
        self.assertEqual("error", result.status)
        self.assertEqual("UNKNOWN_USER", result.reason_code)


class _CapturingResult:
    def __init__(self, *, scalar: int | None = None, row: dict[str, object] | None = None) -> None:
        self.scalar = scalar
        self.row = row

    def scalar_one(self) -> int:
        assert self.scalar is not None
        return self.scalar

    def mappings(self) -> "_CapturingResult":
        return self

    def one(self) -> dict[str, object]:
        assert self.row is not None
        return self.row


class _CapturingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.returned_row = {
            "ticket_id": "IT-5001", "requester_id": "u001", "department": "it", "category": "vpn",
            "priority": "normal", "status": "open", "assigned_to": None,
            "created_at": "2026-02-16T00:00:00+00:00", "updated_at": "2026-02-16T00:00:00+00:00", "visibility_scope": "own",
        }

    def execute(self, query, parameters):
        sql = str(query)
        self.calls.append((sql, dict(parameters)))
        if "MAX((regexp_match" in sql:
            return _CapturingResult(scalar=5001)
        if "RETURNING" in sql:
            return _CapturingResult(row=self.returned_row)
        return _CapturingResult()


class _CapturingTransaction:
    def __init__(self, connection: _CapturingConnection) -> None:
        self.connection = connection

    def __enter__(self) -> _CapturingConnection:
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        return None


class _CapturingEngine:
    def __init__(self) -> None:
        self.connection = _CapturingConnection()

    def begin(self) -> _CapturingTransaction:
        return _CapturingTransaction(self.connection)


if __name__ == "__main__":
    unittest.main()
