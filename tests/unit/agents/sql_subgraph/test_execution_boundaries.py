import unittest

from app.agents.sql_subgraph.graph import SQLSubgraph
from app.agents.sql_subgraph.state import SQLExecutionResult, UserContext


class CapturingExecutor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object], int]] = []

    def fetch_one(self, query, parameters):
        return None

    def fetch_all(self, query, parameters, max_rows):
        self.calls.append((query, dict(parameters), max_rows))
        return SQLExecutionResult(
            columns=("region", "holiday_name", "date"),
            rows=({"region": "Pakistan", "holiday_name": "Fixture Day", "date": "2026-01-01"},),
            row_count=1,
            elapsed_ms=2,
        )


class SQLExecutionBoundaryTest(unittest.TestCase):
    def test_live_executor_receives_validated_query_and_bound_parameters(self) -> None:
        executor = CapturingExecutor()
        graph = SQLSubgraph(executor=executor)

        output = graph.invoke(
            {
                "user_id": "u001",
                "question": "What holidays apply in Pakistan?",
                "user_context": UserContext(
                    user_id="u001",
                    role="employee",
                    department="engineering",
                    location="Pakistan",
                ),
                "execute": True,
            }
        )

        self.assertEqual("answered", output.sql_status)
        self.assertEqual(1, len(executor.calls))
        query, parameters, max_rows = executor.calls[0]
        self.assertIn("company_holidays", query)
        self.assertNotIn("SELECT *", query.upper())
        self.assertEqual("Pakistan", parameters["region"])
        self.assertEqual(25, max_rows)
        self.assertEqual("Fixture Day", output.sql_rows[0]["holiday_name"])

    def test_missing_context_is_refused_before_planning_or_execution(self) -> None:
        output = SQLSubgraph().invoke(
            {
                "user_id": "u001",
                "question": "What holidays apply in Pakistan?",
                "execute": False,
            }
        )

        self.assertEqual("refused", output.sql_status)
        self.assertIn("User context is required", output.sql_denied_reason or "")

    def test_unsupported_structured_request_requires_clarification(self) -> None:
        output = SQLSubgraph().invoke(
            {
                "user_id": "u001",
                "question": "Tell me something unrelated to the structured connector.",
                "user_context": UserContext(
                    user_id="u001",
                    role="employee",
                    department="engineering",
                    location="Pakistan",
                ),
                "execute": False,
            }
        )

        self.assertEqual("needs_clarification", output.sql_status)
        self.assertNotIn("SELECT", output.sql_query or "")


if __name__ == "__main__":
    unittest.main()
