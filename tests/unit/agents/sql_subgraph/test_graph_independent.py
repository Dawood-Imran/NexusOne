import unittest

from app.agents.sql_subgraph.graph import SQLSubgraph, clean_question_text
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


class PlannerWithUnsafeFirstDraft:
    def classify_intent(self, question, requested_intent, known_intents):
        return "ticket_status"

    def draft_sql(self, question, intent, schema_context, allowed_sources, user_id):
        return (
            "SELECT ticket_id, requester_id, assigned_to, status "
            "FROM accessible_tickets(:user_id) ORDER BY updated_at DESC LIMIT 25",
            {"user_id": user_id},
        )

    def repair_sql(
        self,
        question,
        intent,
        schema_context,
        allowed_sources,
        previous_sql,
        previous_parameters,
        feedback,
        user_id,
    ):
        return (
            "SELECT ticket_id, department, category, priority, status, updated_at "
            "FROM accessible_tickets(:user_id) ORDER BY updated_at DESC LIMIT 25",
            {"user_id": user_id},
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
        self.assertIn("validate_sql_safety", [trace.node_name for trace in run.traces])
        self.assertEqual("check_answer_grounding", run.traces[-1].node_name)

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

    def test_ticket_id_assignment_question_routes_to_ticket_status_without_planner(self) -> None:
        graph = SQLSubgraph()

        output = graph.invoke(
            {
                "conversation_id": "c1",
                "turn_id": "t-assignment",
                "user_id": "u001",
                "question": "Who is assigned to IT-1046?",
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
        self.assertIn("accessible_ticket_assignments", output.sql_used_tables)
        self.assertEqual("IT-1046", output.sql_parameters["ticket_id"])

    def test_ticket_handling_question_with_terminal_escape_routes_to_assignment_source(self) -> None:
        graph = SQLSubgraph()

        output = graph.invoke(
            {
                "conversation_id": "c1",
                "turn_id": "t-handling",
                "user_id": "u001",
                "question": "can you tell me who is handling ticker IT-1046 ??\x1b[D\x1b[D",
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
        self.assertIn("accessible_ticket_assignments", output.sql_used_tables)
        self.assertEqual("IT-1046", output.sql_parameters["ticket_id"])

    def test_clean_question_text_removes_terminal_escape_artifacts(self) -> None:
        self.assertEqual(
            "can you tell me who is handling ticker IT-1046 ??",
            clean_question_text("can you tell me who is handling ticker IT-1046 ??\x1b[D^[[D"),
        )

    def test_validation_feedback_repairs_hidden_ticket_columns(self) -> None:
        graph = SQLSubgraph(planner=PlannerWithUnsafeFirstDraft())

        run = graph.invoke_with_trace(
            {
                "conversation_id": "c1",
                "turn_id": "t6",
                "user_id": "u001",
                "question": "Show my ticket status.",
                "user_context": UserContext(
                    user_id="u001",
                    role="employee",
                    department="engineering",
                    location="Pakistan",
                ),
                "execute": False,
            }
        )

        self.assertEqual("validated", run.output.sql_status)
        self.assertEqual(1, run.traces[-1].details["repair_attempts"])
        self.assertIn("repair_sql", [trace.node_name for trace in run.traces])
        self.assertNotIn("requester_id", run.output.sql_query or "")
        self.assertNotIn("assigned_to", run.output.sql_query or "")


if __name__ == "__main__":
    unittest.main()
