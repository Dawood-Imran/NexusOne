import unittest

from app.agents.sql_subgraph.presentation import (
    format_safe_terminal_answer,
    format_timestamp_for_user,
    safe_summary_payload,
    sanitized_rows,
)
from app.agents.sql_subgraph.state import SQLSubgraphOutput


class PresentationTest(unittest.TestCase):
    def test_timestamp_formatter_preserves_utc_contract_across_inputs(self) -> None:
        self.assertEqual("Feb 7, 2026, 9:00 AM UTC", format_timestamp_for_user("2026-02-07T09:00:00Z"))
        self.assertEqual("Feb 7, 2026, 3:30 AM UTC", format_timestamp_for_user("2026-02-07T09:00:00+05:30"))
        self.assertEqual("Feb 7, 2026, 9:00 AM UTC", format_timestamp_for_user("2026-02-07 09:00:00 UT"))
        self.assertEqual("Timestamp unavailable", format_timestamp_for_user("not-a-timestamp"))
        self.assertEqual("Timestamp unavailable", format_timestamp_for_user("2026-02-30"))
        self.assertEqual("Timestamp unavailable", format_timestamp_for_user(""))

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

    def test_ticket_answer_skips_missing_optional_fields(self) -> None:
        output = SQLSubgraphOutput(
            sql_status="answered",
            sql_answer_summary="Structured query returned 2 row(s).",
            sql_rows=(
                {"ticket_id": "IT-1046", "status": "open", "updated_at": "2026-02-15"},
                {"ticket_id": "IT-1042", "status": "open", "updated_at": "2026-02-10"},
            ),
            sql_columns=("ticket_id", "status", "updated_at"),
            sql_sources=({"name": "accessible_tickets", "kind": "function", "domain": "ticket_status"},),
            sql_used_tables=("accessible_tickets",),
        )

        answer = format_safe_terminal_answer(output)

        self.assertIn("IT-1046: open", answer)
        self.assertNotIn("None", answer)

    def test_ticket_assignment_question_hides_raw_assignee_id(self) -> None:
        output = SQLSubgraphOutput(
            sql_status="answered",
            sql_answer_summary="Structured query returned 1 row(s).",
            sql_rows=(
                {"ticket_id": "IT-1046", "status": "open", "assigned_to": "u005"},
            ),
            sql_columns=("ticket_id", "status", "assigned_to"),
            sql_sources=({"name": "accessible_tickets", "kind": "function", "domain": "ticket_status"},),
            sql_used_tables=("accessible_tickets",),
        )

        answer = format_safe_terminal_answer(output, question="Who is assigned to IT-1046?")

        self.assertIn("cannot show internal", answer)
        self.assertNotIn("u005", answer)

    def test_ticket_assignment_question_can_show_safe_assignee_name(self) -> None:
        output = SQLSubgraphOutput(
            sql_status="answered",
            sql_answer_summary="Structured query returned 1 row(s).",
            sql_rows=(
                {
                    "ticket_id": "IT-1046",
                    "status": "open",
                    "assignee_name": "Maya Chen",
                    "assignee_title": "IT Support Engineer",
                    "assignee_department": "it",
                    "updated_at": "2026-02-15 10:40:00+00:00",
                },
            ),
            sql_columns=("ticket_id", "status", "assignee_name", "assignee_title", "assignee_department", "updated_at"),
            sql_sources=({"name": "accessible_ticket_assignments", "kind": "function", "domain": "ticket_status"},),
            sql_used_tables=("accessible_ticket_assignments",),
        )

        answer = format_safe_terminal_answer(output, question="Who is assigned to IT-1046?")

        self.assertIn("Ticket IT-1046 is assigned to Maya Chen", answer)
        self.assertNotIn("cannot show internal", answer)

    def test_ticket_handling_question_can_show_safe_assignee_name(self) -> None:
        output = SQLSubgraphOutput(
            sql_status="answered",
            sql_answer_summary="Structured query returned 1 row(s).",
            sql_rows=(
                {
                    "ticket_id": "IT-1046",
                    "assignee_name": "Maya Chen",
                    "assignee_title": "IT Support Engineer",
                    "assignee_department": "it",
                },
            ),
            sql_columns=("ticket_id", "assignee_name", "assignee_title", "assignee_department"),
            sql_sources=({"name": "accessible_ticket_assignments", "kind": "function", "domain": "ticket_status"},),
            sql_used_tables=("accessible_ticket_assignments",),
        )

        answer = format_safe_terminal_answer(output, question="Who is handling ticker IT-1046?")

        self.assertIn("Ticket IT-1046 is assigned to Maya Chen", answer)
        self.assertNotIn("None", answer)

    def test_ticket_status_missing_status_does_not_print_none(self) -> None:
        output = SQLSubgraphOutput(
            sql_status="answered",
            sql_answer_summary="Structured query returned 1 row(s).",
            sql_rows=({"ticket_id": "IT-1046"},),
            sql_columns=("ticket_id",),
            sql_sources=({"name": "accessible_tickets", "kind": "function", "domain": "ticket_status"},),
            sql_used_tables=("accessible_tickets",),
        )

        answer = format_safe_terminal_answer(output, question="Show ticket IT-1046")

        self.assertIn("Ticket IT-1046 matched the request", answer)
        self.assertNotIn("None", answer)

    def test_empty_specific_ticket_result_is_accessible_not_found_message(self) -> None:
        output = SQLSubgraphOutput(
            sql_status="answered",
            sql_answer_summary="Structured query returned 0 row(s).",
            sql_rows=(),
            sql_columns=("ticket_id", "status", "assignee_name"),
            sql_sources=({"name": "accessible_ticket_assignments", "kind": "function", "domain": "ticket_status"},),
            sql_used_tables=("accessible_ticket_assignments",),
        )

        answer = format_safe_terminal_answer(output, question="Who is assigned to HR-2034?")

        self.assertEqual("I could not find an accessible matching ticket.", answer)


if __name__ == "__main__":
    unittest.main()
