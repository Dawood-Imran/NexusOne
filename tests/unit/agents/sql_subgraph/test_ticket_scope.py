from __future__ import annotations

import unittest
from typing import Any, Mapping

from app.agents.sql_subgraph.graph import SQLSubgraph
from app.agents.sql_subgraph.presentation import format_safe_terminal_answer
from app.agents.sql_subgraph.state import SQLExecutionResult, UserContext


class ScopedTicketExecutor:
    """Offline stand-in for the database's permission-safe ticket functions."""

    rows = (
        {"ticket_id": "IT-9001", "requester_id": "u001", "department": "it", "category": "battery", "priority": "normal", "status": "open", "updated_at": "2026-02-07T09:00:00+00:00"},
        {"ticket_id": "IT-9002", "requester_id": "u002", "department": "it", "category": "vpn", "priority": "high", "status": "in_progress", "updated_at": "2026-02-08T09:00:00+00:00"},
        {"ticket_id": "HR-9003", "requester_id": "u003", "department": "hr", "category": "payroll", "priority": "normal", "status": "open", "updated_at": "2026-02-09T09:00:00+00:00"},
        {"ticket_id": "IT-9004", "requester_id": "u004", "department": "it", "category": "device", "priority": "normal", "status": "closed", "updated_at": "2026-02-10T09:00:00+00:00"},
    )

    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, dict[str, Any]]] = []
        self.fetch_all_calls: list[tuple[str, dict[str, Any], int]] = []

    def fetch_one(self, query: str, parameters: Mapping[str, Any]) -> Mapping[str, Any] | None:
        self.fetch_one_calls.append((query, dict(parameters)))
        # The real users table returns no row for malformed or unknown IDs.
        user_id = parameters.get("user_id")
        if user_id not in {"u001", "u002", "u003", "u004"}:
            return None
        return None

    def fetch_all(self, query: str, parameters: Mapping[str, Any], max_rows: int) -> SQLExecutionResult:
        self.fetch_all_calls.append((query, dict(parameters), max_rows))
        user_id = parameters.get("user_id")
        ticket_id = parameters.get("ticket_id")
        # This mirrors can_user_access_ticket for the fixture users: u001 owns
        # one ticket, while u002 is its manager and may also see u001's row.
        if user_id == "u001":
            visible = [row for row in self.rows if row["requester_id"] == "u001"]
        elif user_id == "u002":
            visible = [row for row in self.rows if row["requester_id"] in {"u001", "u002"}]
        else:
            visible = [row for row in self.rows if row["requester_id"] == user_id]
        if ticket_id is not None:
            visible = [row for row in visible if row["ticket_id"] == ticket_id]
        return SQLExecutionResult(
            columns=tuple(visible[0].keys()) if visible else ("ticket_id", "status", "updated_at"),
            rows=tuple(visible[:max_rows]),
            row_count=len(visible[:max_rows]),
            elapsed_ms=1,
        )


class TicketScopeRegressionTest(unittest.TestCase):
    @staticmethod
    def context(user_id: str, role: str = "employee") -> UserContext:
        return UserContext(
            user_id=user_id,
            role=role,
            department="engineering" if role in {"employee", "manager"} else "hr",
            location="Pakistan",
            groups=("all_employees",),
        )

    def test_authenticated_employee_list_is_scoped_to_requester(self) -> None:
        executor = ScopedTicketExecutor()
        output = SQLSubgraph(executor=executor).invoke(
            {"user_id": "u001", "question": "Show my ticket status.", "user_context": self.context("u001"), "execute": True}
        )

        self.assertEqual("answered", output.sql_status)
        self.assertEqual({"IT-9001"}, {row["ticket_id"] for row in output.sql_rows})
        self.assertNotIn("IT-9002", output.sql_query or "")
        self.assertEqual("u001", output.sql_parameters["user_id"])
        self.assertEqual("accessible_tickets", output.sql_used_tables[0])

    def test_manager_mixed_result_keeps_role_scope_without_unrelated_users(self) -> None:
        executor = ScopedTicketExecutor()
        output = SQLSubgraph(executor=executor).invoke(
            {"user_id": "u002", "question": "List my ticket statuses.", "user_context": self.context("u002", "manager"), "execute": True}
        )

        self.assertEqual({"IT-9001", "IT-9002"}, {row["ticket_id"] for row in output.sql_rows})
        self.assertNotIn("HR-9003", {row["ticket_id"] for row in output.sql_rows})
        self.assertNotIn("IT-9004", {row["ticket_id"] for row in output.sql_rows})
        query, params, _ = executor.fetch_all_calls[0]
        self.assertIn("accessible_tickets(:user_id)", query)
        self.assertEqual({"user_id": "u002"}, params)

    def test_empty_result_for_another_users_ticket_does_not_confirm_record(self) -> None:
        executor = ScopedTicketExecutor()
        output = SQLSubgraph(executor=executor).invoke(
            {"user_id": "u001", "question": "Show ticket IT-9002 status.", "user_context": self.context("u001"), "execute": True}
        )

        self.assertEqual("answered", output.sql_status)
        self.assertEqual((), output.sql_rows)
        self.assertEqual(
            "I could not find an accessible matching ticket.",
            format_safe_terminal_answer(output, question="Show ticket IT-9002 status."),
        )

    def test_malformed_user_is_bound_and_refused_before_ticket_query(self) -> None:
        executor = ScopedTicketExecutor()
        malformed = "u001' OR '1'='1"
        output = SQLSubgraph(executor=executor).invoke(
            {"user_id": malformed, "question": "List my tickets.", "execute": True}
        )

        self.assertEqual("refused", output.sql_status)
        self.assertEqual(1, len(executor.fetch_one_calls))
        _, params = executor.fetch_one_calls[0]
        self.assertEqual({"user_id": malformed}, params)
        self.assertEqual([], executor.fetch_all_calls)

    def test_mismatched_context_cannot_change_authenticated_ticket_parameter(self) -> None:
        executor = ScopedTicketExecutor()
        output = SQLSubgraph(executor=executor).invoke(
            {
                "user_id": "u001",
                "question": "List my tickets.",
                "user_context": self.context("u002", "manager"),
                "execute": True,
            }
        )

        self.assertEqual("refused", output.sql_status)
        self.assertIn("does not match", output.sql_denied_reason or "")
        self.assertEqual([], executor.fetch_one_calls)
        self.assertEqual([], executor.fetch_all_calls)

    def test_injection_like_ticket_text_stays_a_bound_ticket_id(self) -> None:
        executor = ScopedTicketExecutor()
        output = SQLSubgraph(executor=executor).invoke(
            {
                "user_id": "u001",
                "question": "Show ticket IT-9001' OR '1'='1 status.",
                "user_context": self.context("u001"),
                "execute": True,
            }
        )

        self.assertEqual("answered", output.sql_status)
        self.assertEqual(["IT-9001"], [row["ticket_id"] for row in output.sql_rows])
        self.assertEqual("IT-9001", output.sql_parameters["ticket_id"])
        self.assertNotIn("OR '1'", output.sql_query or "")

    def test_local_validation_only_keeps_scoped_function_and_no_rows(self) -> None:
        output = SQLSubgraph().invoke(
            {"user_id": "u001", "question": "List my tickets.", "user_context": self.context("u001"), "execute": False}
        )

        self.assertEqual("validated", output.sql_status)
        self.assertEqual((), output.sql_rows)
        self.assertIn("accessible_tickets(:user_id)", output.sql_query or "")
        self.assertEqual("u001", output.sql_parameters["user_id"])


if __name__ == "__main__":
    unittest.main()
