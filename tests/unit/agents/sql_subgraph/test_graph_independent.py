import unittest

from app.agents.sql_subgraph.graph import SQLSubgraph
from app.agents.sql_subgraph.state import UserContext


class PlannerWithBadUserIdParameter:
    def classify_intent(self, question, requested_intent, known_intents):
        return "ticket_status"

    def draft_sql(self, question, intent, schema_context, allowed_sources, user_id):
        return (
            "SELECT ticket_id, status FROM accessible_tickets(:user_id) "
            "WHERE ticket_id = :ticket_id LIMIT 1",
            {"user_id": ":user_id", "ticket_id": "IT-1046"},
        )


class IndependentSQLSubgraphTest(unittest.TestCase):
    def test_public_holiday_question_validates_without_executor(self) -> None:
        graph = SQLSubgraph()

        output = graph.invoke(
            {
                "conversation_id": "c1",
                "turn_id": "t1",
                "user_id": "u001",
                "question": "What holidays apply in Pakistan?",
                "user_context": {
                    "user_id": "u001",
                    "role": "employee",
                    "department": "engineering",
                    "location": "Pakistan",
                    "groups": ["all_employees"],
                },
                "execute": False,
            }
        )

        self.assertEqual("validated", output.sql_status)
        self.assertIn("company_holidays", output.sql_used_tables)
        self.assertEqual("Pakistan", output.sql_parameters["region"])

    def test_employee_finance_budget_question_is_denied(self) -> None:
        graph = SQLSubgraph()

        output = graph.invoke(
            {
                "conversation_id": "c1",
                "turn_id": "t2",
                "user_id": "u001",
                "question": "Show department budget utilization.",
                "user_context": UserContext(
                    user_id="u001",
                    role="employee",
                    department="engineering",
                    location="Pakistan",
                ),
                "execute": False,
            }
        )

        self.assertEqual("no_allowed_source", output.sql_status)
        self.assertIn("not allowed", output.sql_denied_reason or "")

    def test_finance_budget_question_validates_without_executor(self) -> None:
        graph = SQLSubgraph()

        output = graph.invoke(
            {
                "conversation_id": "c1",
                "turn_id": "t3",
                "user_id": "u005",
                "question": "Show department budget utilization.",
                "user_context": UserContext(
                    user_id="u005",
                    role="finance",
                    department="finance",
                    location="Pakistan",
                ),
                "execute": False,
            }
        )

        self.assertEqual("validated", output.sql_status)
        self.assertIn("department_budgets", output.sql_used_tables)
        self.assertIn("SELECT", output.sql_query or "")

    def test_graph_definition_is_separate_and_explicit(self) -> None:
        graph = SQLSubgraph()
        definition = graph.graph_definition()

        self.assertIn("load_user_context", definition["nodes"])
        self.assertIn(("validate_sql_safety", "execute_or_package"), definition["edges"])

    def test_graph_returns_node_trace(self) -> None:
        graph = SQLSubgraph()

        run = graph.invoke_with_trace(
            {
                "conversation_id": "c1",
                "turn_id": "t4",
                "user_id": "u001",
                "question": "What holidays apply in Pakistan?",
                "user_context": {
                    "user_id": "u001",
                    "role": "employee",
                    "department": "engineering",
                    "location": "Pakistan",
                },
                "execute": False,
            }
        )

        self.assertEqual("validated", run.output.sql_status)
        self.assertGreaterEqual(len(run.traces), 6)
        self.assertEqual("load_user_context", run.traces[0].node_name)
        self.assertEqual("validate_sql_safety", run.traces[-2].node_name)

    def test_planner_cannot_override_trusted_user_id_parameter(self) -> None:
        graph = SQLSubgraph(planner=PlannerWithBadUserIdParameter())

        output = graph.invoke(
            {
                "conversation_id": "c1",
                "turn_id": "t5",
                "user_id": "u001",
                "question": "Show ticket IT-1046 status.",
                "user_context": UserContext(
                    user_id="u001",
                    role="employee",
                    department="engineering",
                    location="Pakistan",
                ),
                "execute": False,
            }
        )

        self.assertEqual("validated", output.sql_status)
        self.assertEqual("u001", output.sql_parameters["user_id"])
        self.assertEqual("IT-1046", output.sql_parameters["ticket_id"])


if __name__ == "__main__":
    unittest.main()
