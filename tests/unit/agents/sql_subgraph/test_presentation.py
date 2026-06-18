import unittest

from app.agents.sql_subgraph.presentation import format_safe_terminal_answer, safe_summary_payload, sanitized_rows
from app.agents.sql_subgraph.state import SQLSubgraphOutput


class PresentationTest(unittest.TestCase):
    def test_ticket_answer_hides_user_reference_columns(self) -> None:
        output = SQLSubgraphOutput(
            sql_status="answered",
            sql_answer_summary="Structured query returned 1 row(s).",
            sql_rows=(
                {
                    "ticket_id": "IT-1046",
                    "requester_id": "u001",
                    "department": "it",
                    "category": "aws_access",
                    "priority": "normal",
                    "status": "open",
                    "assigned_to": "u005",
                    "updated_at": "2026-02-15 10:40:00+00:00",
                },
            ),
            sql_columns=("ticket_id", "requester_id", "department", "category", "priority", "status", "assigned_to", "updated_at"),
            sql_sources=({"name": "accessible_tickets", "kind": "function", "domain": "ticket_status"},),
            sql_used_tables=("accessible_tickets",),
        )

        rows = sanitized_rows(output)
        answer = format_safe_terminal_answer(output)
        payload = safe_summary_payload("Show ticket IT-1046 status", output)

        self.assertNotIn("requester_id", rows[0])
        self.assertNotIn("assigned_to", rows[0])
        self.assertNotIn("u001", answer)
        self.assertNotIn("u005", answer)
        self.assertNotIn("assigned_to", str(payload))
        self.assertNotIn("sources", payload)
        self.assertIn("Ticket IT-1046 is open", answer)


if __name__ == "__main__":
    unittest.main()
