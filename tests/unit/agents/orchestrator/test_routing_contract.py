import unittest

from app.agents.orchestrator.action_routing import extract_ticket_request, wants_ticket_creation
from app.agents.orchestrator.routing import route_message


class OrchestratorRoutingContractTest(unittest.TestCase):
    def test_all_reachable_routes_have_stable_deterministic_examples(self) -> None:
        examples = {
            "ticket_create": "Please open an IT ticket for a laptop replacement.",
            "CASUAL": "Thanks so much!",
            "sql": "What holidays apply in Pakistan?",
            "combined": "What holidays apply in Pakistan and how do I request AWS access?",
            "GENERAL_KNOWLEDGE": "How does TCP work?",
            "rag": "How do I request AWS access?",
        }
        for route, message in examples.items():
            with self.subTest(route=route):
                self.assertEqual(route, route_message(message))

    def test_internal_reference_beats_general_knowledge_and_exact_structured_question(self) -> None:
        self.assertEqual("rag", route_message("What is our company's vacation policy?"))
        self.assertEqual("sql", route_message("How many employees are in Engineering?"))
        self.assertEqual("rag", route_message("How does NexusOne's ticket system work?"))

    def test_ticket_extraction_normalizes_fields_without_accepting_short_description(self) -> None:
        request = extract_ticket_request(
            "Create a high priority IT ticket for AWS access because billing migration needs sandbox access."
        )

        self.assertEqual("it", request.department)
        self.assertEqual("cloud_access", request.category)
        self.assertEqual("high", request.priority)
        self.assertIn("billing migration", request.description or "")
        self.assertTrue(wants_ticket_creation("raise a case for my VPN"))
        self.assertFalse(wants_ticket_creation("show my ticket status"))

    def test_ticket_description_does_not_preserve_command_prefix(self) -> None:
        request = extract_ticket_request("Open an HR ticket for a payroll correction needed this month.")

        self.assertEqual("hr", request.department)
        self.assertNotIn("Open an HR ticket", request.description or "")
        self.assertIn("payroll correction", request.description or "")


if __name__ == "__main__":
    unittest.main()
