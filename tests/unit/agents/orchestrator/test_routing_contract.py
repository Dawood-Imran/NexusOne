import unittest

from app.agents.orchestrator.action_routing import extract_ticket_request
from app.agents.orchestrator.intent_classifier import IntentClassificationResult
from app.agents.orchestrator.routing import route_from_intent


class OrchestratorRoutingContractTest(unittest.TestCase):
    def test_finite_intent_labels_map_to_stable_routes(self) -> None:
        routes = {
            "casual": "CASUAL",
            "general_question": "GENERAL_KNOWLEDGE",
            "knowledge_lookup": "rag",
            "ticket_guidance": "ticket_guidance",
            "structured_lookup": "sql",
            "combined_lookup": "combined",
            "ticket_create": "ticket_create",
            "ticket_status": "sql",
            "history_lookup": "unsupported",
            "feedback": "feedback",
            "clarification": "clarification",
            "unsupported": "unsupported",
        }
        for intent, route in routes.items():
            with self.subTest(intent=intent):
                result = IntentClassificationResult(
                    intent=intent,  # type: ignore[arg-type]
                    confidence=0.99,
                    needs_clarification=False,
                    clarification_question=None,
                    missing_context=(),
                )
                self.assertEqual(route, route_from_intent(result))

    def test_clarification_flag_prevents_guessing_protected_routes(self) -> None:
        result = IntentClassificationResult(
            intent="structured_lookup",
            confidence=0.8,
            needs_clarification=True,
            clarification_question="Which lookup do you mean?",
            missing_context=("dataset",),
        )
        self.assertEqual("clarification", route_from_intent(result))

    def test_ticket_creation_and_status_are_distinct_contract_labels(self) -> None:
        create = IntentClassificationResult(
            intent="ticket_create", confidence=0.99, needs_clarification=False,
            clarification_question=None, missing_context=(),
        )
        status = IntentClassificationResult(
            intent="ticket_status", confidence=0.99, needs_clarification=False,
            clarification_question=None, missing_context=(),
        )
        self.assertEqual("ticket_create", route_from_intent(create))
        self.assertEqual("sql", route_from_intent(status))

    def test_ticket_extraction_normalizes_fields_without_accepting_short_description(self) -> None:
        request = extract_ticket_request(
            "Create a high priority IT ticket for AWS access because billing migration needs sandbox access."
        )

        self.assertEqual("it", request.department)
        self.assertEqual("cloud_access", request.category)
        self.assertEqual("high", request.priority)
        self.assertIn("billing migration", request.description or "")

    def test_ticket_description_does_not_preserve_command_prefix(self) -> None:
        request = extract_ticket_request("Open an HR ticket for a payroll correction needed this month.")

        self.assertEqual("hr", request.department)
        self.assertNotIn("Open an HR ticket", request.description or "")
        self.assertIn("payroll correction", request.description or "")


if __name__ == "__main__":
    unittest.main()
