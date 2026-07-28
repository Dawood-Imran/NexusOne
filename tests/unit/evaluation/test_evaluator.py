import copy
import unittest

from tests.evaluation.evaluator import (
    DEFAULT_DATASET_PATH,
    DIMENSIONS,
    LiveEvaluationRefused,
    load_dataset,
    run_deterministic_evaluation,
    run_live_evaluation,
    validate_dataset,
)


class OfflineEvaluationTest(unittest.TestCase):
    def test_dataset_declares_required_surface_and_server_roles(self) -> None:
        dataset = load_dataset(DEFAULT_DATASET_PATH)
        ids = {case["id"] for case in dataset["cases"]}

        self.assertGreaterEqual(len(ids), 12)
        self.assertIn("public-aws-access-employee", ids)
        self.assertIn("executive-denied-employee", ids)
        self.assertIn("prompt-injection-denied-before-tools", ids)
        self.assertIn("no-provider-unsupported-general-question", ids)
        self.assertEqual(DIMENSIONS, tuple(dataset["dimensions"]))

    def test_deterministic_dataset_passes_without_provider_or_database(self) -> None:
        report = run_deterministic_evaluation()

        self.assertTrue(report.passed)
        self.assertEqual(20, len(report.cases))
        self.assertEqual(20, report.dimension_totals()["authorization"]["passed"])
        self.assertEqual(20, report.dimension_totals()["safety_no_leakage"]["passed"])
        self.assertNotIn("message", report.to_dict()["cases"][0])

    def test_dataset_validator_rejects_role_drift(self) -> None:
        dataset = copy.deepcopy(load_dataset(DEFAULT_DATASET_PATH))
        dataset["cases"][0]["role"] = "ceo"

        with self.assertRaises(ValueError):
            validate_dataset(dataset)

    def test_live_evaluation_refuses_without_both_opt_in_and_credentials(self) -> None:
        with self.assertRaises(LiveEvaluationRefused):
            run_live_evaluation([], lambda _case: {}, environ={})

    def test_live_judge_cannot_override_deterministic_safety_failure(self) -> None:
        dataset = load_dataset(DEFAULT_DATASET_PATH)
        case = next(item for item in dataset["cases"] if item["id"] == "executive-denied-employee")
        response = {
            "status": "denied",
            "reason_code": "ROLE_NOT_AUTHORIZED",
            "route": "deny",
            "category": "executive",
            "message": "I cannot access that information for your role. Q4 Revenue Risk Register details.",
            "latency_ms": 1,
            "profile": {"user_id": "u001", "role": "employee"},
            "trace": [],
        }

        results = run_live_evaluation(
            [case],
            lambda _case: response,
            judge=lambda _case, _response: True,
            environ={"NEXUSONE_ENABLE_LIVE_EVAL": "1", "OPENAI_API_KEY": "sk-live-fixture"},
        )

        self.assertFalse(results[0].passed)
        self.assertFalse(next(item for item in results[0].dimensions if item.name == "safety_no_leakage").passed)
        self.assertNotIn("Q4 Revenue Risk Register", repr(results[0]))


if __name__ == "__main__":
    unittest.main()
