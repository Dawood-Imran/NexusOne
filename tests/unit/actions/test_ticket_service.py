import unittest

from app.actions.ticket_service import InMemoryTicketRepository, TicketRequest, TicketService
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


if __name__ == "__main__":
    unittest.main()
