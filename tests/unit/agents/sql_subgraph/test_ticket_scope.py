from __future__ import annotations

from pathlib import Path
import unittest
from typing import Any, Mapping

from app.agents.sql_subgraph.graph import SQLSubgraph
from app.agents.sql_subgraph.presentation import format_safe_terminal_answer
from app.agents.sql_subgraph.state import SQLExecutionResult, UserContext


class ScopedTicketExecutor:
    """Offline stand-in for the database's permission-safe ticket functions."""

    rows = (
        {"ticket_id": "IT-9001", "requester_id": "u001", "department": "it", "category": "battery", "priority": "normal", "status": "open", "assigned_to": "u005", "updated_at": "2026-02-07T09:00:00+00:00"},
        {"ticket_id": "IT-9002", "requester_id": "u002", "department": "it", "category": "vpn", "priority": "high", "status": "in_progress", "assigned_to": "u005", "updated_at": "2026-02-08T09:00:00+00:00"},
        {"ticket_id": "HR-9003", "requester_id": "u003", "department": "hr", "category": "payroll", "priority": "normal", "status": "open", "assigned_to": "u003", "updated_at": "2026-02-09T09:00:00+00:00"},
        {"ticket_id": "HR-9004", "requester_id": "u004", "department": "hr", "category": "benefits", "priority": "normal", "status": "open", "assigned_to": "u003", "updated_at": "2026-02-09T10:00:00+00:00"},
        {"ticket_id": "IT-9005", "requester_id": "u004", "department": "it", "category": "device", "priority": "normal", "status": "closed", "assigned_to": None, "updated_at": "2026-02-10T09:00:00+00:00"},
    )

    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, dict[str, Any]]] = []
        self.fetch_all_calls: list[tuple[str, dict[str, Any], int]] = []

    def fetch_one(self, query: str, parameters: Mapping[str, Any]) -> Mapping[str, Any] | None:
        self.fetch_one_calls.append((query, dict(parameters)))
        # The real users table returns no row for malformed or unknown IDs.
        return None

    def fetch_all(self, query: str, parameters: Mapping[str, Any], max_rows: int) -> SQLExecutionResult:
        self.fetch_all_calls.append((query, dict(parameters), max_rows))
        user_id = parameters.get("user_id")
        ticket_id = parameters.get("ticket_id")
        if user_id == "u005":
            # IT admins receive their own tickets and tickets assigned to them
            # only inside the IT role/department scope.
            visible = [
                row for row in self.rows
                if row["requester_id"] == user_id
                or (row["assigned_to"] == user_id and row["department"] == "it")
            ]
        elif user_id == "u003":
            # HR receives its own tickets and HR tickets assigned to HR.
            visible = [
                row for row in self.rows
                if row["requester_id"] == user_id
                or (row["assigned_to"] == user_id and row["department"] == "hr")
            ]
        elif user_id == "u006":
            visible = list(self.rows)
        else:
            # Employee, manager, finance, and other ordinary callers are
            # creator-scoped unless a future explicit queue policy is added.
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
        role_details = {
            "employee": ("engineering", ("all_employees",)),
            "manager": ("engineering", ("all_employees", "managers")),
            "it_admin": ("it", ("all_employees", "it_team")),
            "hr": ("hr", ("all_employees", "hr_team")),
            "ceo": ("executive", ("all_employees",)),
        }
        department, groups = role_details.get(role, ("engineering", ("all_employees",)))
        return UserContext(
            user_id=user_id,
            role=role,
            department=department,
            location="Pakistan",
            groups=groups,
        )

    def test_authenticated_employee_list_is_scoped_to_requester(self) -> None:
        executor = ScopedTicketExecutor()
        output = SQLSubgraph(executor=executor).invoke(
            {"user_id": "u001", "question": "Show my ticket status.", "user_context": self.context("u001"), "execute": True}
        )

        self.assertEqual("answered", output.sql_status)
        self.assertEqual({"IT-9001"}, {row["ticket_id"] for row in output.sql_rows})
        self.assertEqual("u001", output.sql_parameters["user_id"])
        self.assertEqual("accessible_tickets", output.sql_used_tables[0])

    def test_manager_is_creator_scoped_not_a_department_queue_reader(self) -> None:
        executor = ScopedTicketExecutor()
        output = SQLSubgraph(executor=executor).invoke(
            {"user_id": "u002", "question": "List my ticket statuses.", "user_context": self.context("u002", "manager"), "execute": True}
        )

        self.assertEqual({"IT-9002"}, {row["ticket_id"] for row in output.sql_rows})
        self.assertNotIn("IT-9001", {row["ticket_id"] for row in output.sql_rows})
        self.assertNotIn("HR-9003", {row["ticket_id"] for row in output.sql_rows})

    def test_it_admin_sees_assigned_it_tickets_but_not_other_departments_or_unassigned(self) -> None:
        executor = ScopedTicketExecutor()
        output = SQLSubgraph(executor=executor).invoke(
            {"user_id": "u005", "question": "List my ticket statuses.", "user_context": self.context("u005", "it_admin"), "execute": True}
        )

        self.assertEqual({"IT-9001", "IT-9002"}, {row["ticket_id"] for row in output.sql_rows})
        self.assertNotIn("HR-9004", {row["ticket_id"] for row in output.sql_rows})
        self.assertNotIn("IT-9005", {row["ticket_id"] for row in output.sql_rows})

    def test_hr_sees_assigned_hr_tickets_but_not_it_tickets(self) -> None:
        executor = ScopedTicketExecutor()
        output = SQLSubgraph(executor=executor).invoke(
            {"user_id": "u003", "question": "List my ticket statuses.", "user_context": self.context("u003", "hr"), "execute": True}
        )

        self.assertEqual({"HR-9003", "HR-9004"}, {row["ticket_id"] for row in output.sql_rows})
        self.assertNotIn("IT-9001", {row["ticket_id"] for row in output.sql_rows})

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

    def test_database_schema_declares_creator_and_shared_predicate(self) -> None:
        root = Path(__file__).resolve().parents[4]
        schema = (root / "data/postgres/init/001_schema.sql").read_text(encoding="utf-8")
        views = (root / "data/postgres/init/005_permission_safe_views.sql").read_text(encoding="utf-8")

        self.assertIn("requester_id text NOT NULL REFERENCES users(user_id)", schema)
        self.assertIn("tickets_requester_immutable", schema)
        self.assertIn("t.requester_id = u.user_id", schema)
        self.assertIn("t.assigned_to = u.user_id", schema)
        self.assertIn("u.role = 'it_admin'", schema)
        self.assertIn("u.role = 'hr'", schema)
        self.assertIn("ug.group_name = 'it_team'", schema)
        self.assertIn("ug.group_name = 'hr_team'", schema)
        self.assertEqual(3, views.count("WHERE can_user_access_ticket(p_user_id"))


if __name__ == "__main__":
    unittest.main()
