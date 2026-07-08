import unittest

from app.agents.sql_subgraph.permissions import select_allowed_sources
from app.agents.sql_subgraph.state import UserContext


class ScopeSelectionTest(unittest.TestCase):
    def test_employee_gets_public_lookup_and_ticket_sources(self) -> None:
        user = UserContext(
            user_id="u001",
            role="employee",
            department="engineering",
            location="Pakistan",
        )

        public_sources = {source.name for source in select_allowed_sources(user, "public_lookup")}
        ticket_sources = {source.name for source in select_allowed_sources(user, "ticket_status")}

        self.assertIn("company_holidays", public_sources)
        self.assertIn("active_employee_directory_public", public_sources)
        self.assertEqual({"accessible_tickets", "accessible_ticket_events", "accessible_ticket_assignments"}, ticket_sources)

    def test_employee_cannot_get_finance_budget_sources(self) -> None:
        user = UserContext(
            user_id="u001",
            role="employee",
            department="engineering",
            location="Pakistan",
        )

        sources = select_allowed_sources(user, "finance_budget")

        self.assertEqual((), sources)

    def test_finance_user_gets_budget_but_not_revenue_risk(self) -> None:
        user = UserContext(
            user_id="u005",
            role="finance",
            department="finance",
            location="Pakistan",
        )

        budget_sources = {source.name for source in select_allowed_sources(user, "finance_budget")}
        revenue_sources = select_allowed_sources(user, "finance_revenue_risk")

        self.assertEqual({"department_budgets"}, budget_sources)
        self.assertEqual((), revenue_sources)

    def test_ceo_gets_revenue_risk_sources(self) -> None:
        user = UserContext(
            user_id="u006",
            role="ceo",
            department="executive",
            location="United States",
        )

        sources = {source.name for source in select_allowed_sources(user, "finance_revenue_risk")}

        self.assertEqual({"revenue_risks"}, sources)


if __name__ == "__main__":
    unittest.main()
