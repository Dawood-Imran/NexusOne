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

    def test_active_user_can_create_it_ticket(self) -> None:
        result = self.service.create_ticket(
            self.profile,
            TicketRequest(
                department="it",
                category="cloud access",
                priority="high",
                description="Need AWS sandbox access for the billing service migration.",
            ),
        )

        self.assertEqual("ticket_created", result.status)
        self.assertEqual("TICKET_CREATED", result.reason_code)
        self.assertIsNotNone(result.ticket)
        assert result.ticket is not None
        self.assertEqual("IT-5001", result.ticket["ticket_id"])
        self.assertEqual("cloud_access", result.ticket["category"])
        self.assertNotIn("requester_id", result.ticket)
        self.assertEqual(1, len(self.repository.tickets))
        self.assertEqual(1, len(self.repository.events))
        self.assertEqual("u001", self.repository.tickets[0]["requester_id"])

    def test_create_path_records_authenticated_creator_and_rejects_scope_spoofing(self) -> None:
        result = self.service.create_ticket(
            self.profile,
            TicketRequest(
                department="it",
                category="vpn",
                priority="normal",
                description="VPN profile keeps failing after password reset today.",
                visibility_scope="department_queue",
            ),
        )

        self.assertEqual("denied", result.status)
        self.assertEqual("TICKET_SCOPE_NOT_ALLOWED", result.reason_code)
        self.assertEqual([], self.repository.tickets)

        created = self.service.create_ticket(
            self.profile,
            TicketRequest(
                department="it",
                category="vpn",
                priority="normal",
                description="VPN profile keeps failing after password reset today.",
            ),
        )

        self.assertEqual("ticket_created", created.status)
        self.assertEqual("u001", self.repository.tickets[0]["requester_id"])
        self.assertEqual("own", self.repository.tickets[0]["visibility_scope"])
        self.assertNotIn("requester_id", created.ticket or {})
        self.assertNotIn("assigned_to", created.ticket or {})

    def test_sql_repository_binds_creator_and_injection_like_description(self) -> None:
        engine = _CapturingEngine()
        repository = SQLAlchemyTicketRepository(engine)
        description = "Need VPN access; DROP TABLE tickets; -- after password reset today."

        result = repository.create_ticket(
            self.profile,
            TicketRequest(
                department="it",
                category="vpn",
                priority="normal",
                description=description,
            ),
        )

        self.assertNotIn("requester_id", result)
        self.assertEqual(3, len(engine.connection.calls))
        ticket_query, ticket_params = engine.connection.calls[1]
        self.assertIn(":requester_id", ticket_query)
        self.assertNotIn(description, ticket_query)
        self.assertEqual("u001", ticket_params["requester_id"])
        self.assertEqual(description, ticket_params["description"])
        self.assertIn("requester_id", engine.connection.returned_row)

    def test_missing_fields_return_clarification(self) -> None:
        result = self.service.create_ticket(
            self.profile,
            TicketRequest(department="it", category=None, priority="normal", description="Open ticket"),
        )

        self.assertEqual("needs_clarification", result.status)
        self.assertEqual(("category", "description"), result.missing_fields)
        self.assertIn("Please provide", result.message)
        self.assertEqual([], self.repository.tickets)

    def test_unsupported_department_is_denied(self) -> None:
        result = self.service.create_ticket(
            self.profile,
            TicketRequest(
                department="finance",
                category="reimbursement",
                priority="normal",
                description="Need help with a reimbursement that is stuck in review.",
            ),
        )

        self.assertEqual("denied", result.status)
        self.assertEqual("UNSUPPORTED_TICKET_DEPARTMENT", result.reason_code)
        self.assertEqual([], self.repository.tickets)

    def test_unknown_user_cannot_create_ticket(self) -> None:
        result = self.service.create_ticket(
            None,
            TicketRequest(
                department="it",
                category="vpn",
                priority="normal",
                description="VPN profile keeps failing after password reset.",
            ),
        )

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
            "ticket_id": "IT-5001",
            "requester_id": "u001",
            "department": "it",
            "category": "vpn",
            "priority": "normal",
            "status": "open",
            "assigned_to": None,
            "created_at": "2026-02-16T00:00:00+00:00",
            "updated_at": "2026-02-16T00:00:00+00:00",
            "visibility_scope": "own",
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
