import unittest

from app.agents.orchestrator import NexusOneOrchestrator
from app.observability.langsmith import RUN_NAME, build_langsmith_config


class LangSmithConfigTest(unittest.TestCase):
    def test_config_contains_safe_metadata_only(self) -> None:
        config = build_langsmith_config(
            {
                "conversation_id": "c-1",
                "turn_id": "t-1",
                "user_id": "u001",
                "message": "Show me payroll data",
                "execute_sql": True,
                "include_trace": True,
                "final_answer": "sensitive answer",
                "citations": [{"text": "source chunk"}],
            }
        )

        self.assertEqual(RUN_NAME, config["run_name"])
        self.assertIn("nexusone", config["tags"])
        self.assertIn("sql-execute", config["tags"])
        self.assertEqual("c-1", config["metadata"]["conversation_id"])
        self.assertEqual("c-1", config["configurable"]["thread_id"])
        self.assertEqual("u001", config["metadata"]["user_id"])
        serialized = repr(config)
        self.assertNotIn("Show me payroll data", serialized)
        self.assertNotIn("sensitive answer", serialized)
        self.assertNotIn("source chunk", serialized)

    def test_route_metadata_accepts_only_safe_route_names(self) -> None:
        casual = build_langsmith_config({"route": "CASUAL"})
        general = build_langsmith_config({"route": "GENERAL_KNOWLEDGE"})
        clarification = build_langsmith_config({"route": "clarification"})
        unsafe = build_langsmith_config({"route": "select * from secrets"})

        self.assertEqual("CASUAL", casual["metadata"]["route"])
        self.assertIn("route:GENERAL_KNOWLEDGE", general["tags"])
        self.assertEqual("clarification", clarification["metadata"]["route"])
        self.assertNotIn("route", unsafe["metadata"])
        self.assertNotIn("select * from secrets", repr(unsafe))

    def test_orchestrator_passes_config_to_graph_invoke(self) -> None:
        orchestrator = NexusOneOrchestrator()
        fake_graph = _FakeGraph()
        orchestrator.graph = fake_graph

        response = orchestrator.invoke(
            {
                "conversation_id": "c-2",
                "turn_id": "t-2",
                "user_id": "u001",
                "message": "How do I request AWS access?",
                "include_trace": False,
            }
        )

        self.assertEqual("answered", response["status"])
        assert fake_graph.config is not None
        self.assertEqual(RUN_NAME, fake_graph.config["run_name"])
        self.assertEqual("c-2", fake_graph.config["metadata"]["conversation_id"])
        self.assertEqual("c-2", fake_graph.config["configurable"]["thread_id"])
        self.assertNotIn("How do I request AWS access?", repr(fake_graph.config))


class _FakeGraph:
    def __init__(self) -> None:
        self.config = None

    def invoke(self, state, config=None):
        self.config = config
        return {
            "response": {
                "status": "answered",
                "message": "ok",
            },
            "trace": (),
        }


if __name__ == "__main__":
    unittest.main()
