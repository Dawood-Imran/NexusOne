import unittest

from app.agents.sql_subgraph.permissions import select_allowed_sources
from app.agents.sql_subgraph.sql_validator import validate_sql
from app.agents.sql_subgraph.state import UserContext


class SQLValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.employee = UserContext(
            user_id="u001",
            role="employee",
            department="engineering",
            location="Pakistan",
        )
        self.finance = UserContext(
            user_id="u005",
            role="finance",
            department="finance",
            location="Pakistan",
        )

    def test_rejects_dml(self) -> None:
        sources = select_allowed_sources(self.finance, "finance_budget")

        result = validate_sql("DELETE FROM department_budgets WHERE department = 'HR'", sources)

        self.assertFalse(result.is_safe)
        self.assertIn("Only SELECT", result.reason or "")

    def test_rejects_multi_statement(self) -> None:
        sources = select_allowed_sources(self.finance, "finance_budget")

        result = validate_sql("SELECT department FROM department_budgets; SELECT * FROM users", sources)

        self.assertFalse(result.is_safe)
        self.assertIn("Multiple SQL statements", result.reason or "")

    def test_rejects_non_allowlisted_source(self) -> None:
        sources = select_allowed_sources(self.employee, "ticket_status")

        result = validate_sql("SELECT ticket_id, status FROM tickets LIMIT 25", sources)

        self.assertFalse(result.is_safe)
        self.assertIn("non-allowlisted", result.reason or "")

    def test_accepts_accessible_ticket_function_with_user_id(self) -> None:
        sources = select_allowed_sources(self.employee, "ticket_status")

        result = validate_sql(
            "SELECT ticket_id, status FROM accessible_tickets(:user_id) ORDER BY updated_at DESC LIMIT 25",
            sources,
        )

        self.assertTrue(result.is_safe)
        self.assertEqual(("accessible_tickets",), result.used_sources)

    def test_rejects_accessible_ticket_function_without_user_id(self) -> None:
        sources = select_allowed_sources(self.employee, "ticket_status")

        result = validate_sql("SELECT ticket_id, status FROM accessible_tickets('u001') LIMIT 25", sources)

        self.assertFalse(result.is_safe)
        self.assertIn(":user_id", result.reason or "")

    def test_accepts_finance_budget_for_finance_user(self) -> None:
        sources = select_allowed_sources(self.finance, "finance_budget")

        result = validate_sql(
            "SELECT period, department, variance FROM department_budgets ORDER BY period DESC LIMIT 25",
            sources,
        )

        self.assertTrue(result.is_safe)
        self.assertEqual(("department_budgets",), result.used_sources)

    def test_rewrites_missing_limit_for_non_aggregate_query(self) -> None:
        sources = select_allowed_sources(self.finance, "finance_budget")

        result = validate_sql("SELECT period, department, variance FROM department_budgets", sources)

        self.assertTrue(result.is_safe)
        self.assertIsNotNone(result.rewritten_sql)
        self.assertIn("LIMIT 25", result.rewritten_sql or "")

    def test_requires_user_id_filter_for_accessible_documents_view(self) -> None:
        sources = select_allowed_sources(self.employee, "document_metadata")

        result = validate_sql("SELECT doc_id, title FROM user_accessible_documents LIMIT 50", sources)

        self.assertFalse(result.is_safe)
        self.assertIn(":user_id", result.reason or "")


if __name__ == "__main__":
    unittest.main()

