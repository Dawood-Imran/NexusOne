from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.memory.tools import MemoryRuntimeContext
from app.memory.user_memory import JSONUserMemoryStore

try:  # The repository's full app dependency includes LangGraph; local storage-only envs may not.
    from langchain_core.messages import AIMessage
    from app.agents.orchestrator.answer_composer import LangChainOpenAIAnswerComposer
except ModuleNotFoundError as exc:  # pragma: no cover - exercised only in dependency-limited shells.
    AIMessage = None  # type: ignore[assignment]
    LangChainOpenAIAnswerComposer = None  # type: ignore[assignment]
    _MISSING_PROVIDER_DEPENDENCY = str(exc)
else:
    _MISSING_PROVIDER_DEPENDENCY = ""


@unittest.skipIf(_MISSING_PROVIDER_DEPENDENCY, f"provider graph dependency unavailable: {_MISSING_PROVIDER_DEPENDENCY}")
class ModelMemoryToolCallTest(unittest.TestCase):
    def test_injected_fake_model_must_call_server_tool_to_save(self) -> None:
        class FakeModel:
            def __init__(self) -> None:
                self.calls = 0

            def bind_tools(self, tools):
                self.tools = tools
                return self

            def invoke(self, _messages):
                self.calls += 1
                if self.calls == 1:
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "update_user_memory",
                                "args": {"name_and_nickname": {"nickname": "Davis"}},
                                "id": "memory-call-1",
                            }
                        ],
                    )
                return AIMessage(content="I saved your nickname.")

        with tempfile.TemporaryDirectory() as directory:
            store = JSONUserMemoryStore(Path(directory) / "profiles")
            composer = LangChainOpenAIAnswerComposer(model=FakeModel(), memory_store=store)
            result = composer.compose(
                {
                    "route": "memory",
                    "question": "My nickname is Davis",
                    "user_memory": {},
                    "_memory_runtime": MemoryRuntimeContext("u001", explicit_user_input=True),
                }
            )
            self.assertEqual(("update_user_memory",), result.tool_calls)
            self.assertEqual(("update_user_memory:ok",), result.tool_outcomes)
            self.assertEqual("Davis", store.read("u001")["name_and_nickname"]["nickname"])

    def test_model_cannot_update_without_explicit_server_flag(self) -> None:
        class FakeModel:
            def __init__(self) -> None:
                self.calls = 0

            def bind_tools(self, tools):
                self.tools = tools
                return self

            def invoke(self, _messages):
                self.calls += 1
                if self.calls == 1:
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "update_user_memory",
                                "args": {"name_and_nickname": {"nickname": "Injected"}},
                                "id": "memory-call-2",
                            }
                        ],
                    )
                return AIMessage(content="I could not save that.")

        with tempfile.TemporaryDirectory() as directory:
            store = JSONUserMemoryStore(Path(directory) / "profiles")
            composer = LangChainOpenAIAnswerComposer(model=FakeModel(), memory_store=store)
            result = composer.compose(
                {
                    "route": "memory",
                    "question": "What is my nickname?",
                    "user_memory": {},
                    "_memory_runtime": MemoryRuntimeContext("u001", explicit_user_input=False),
                }
            )
            self.assertEqual(("update_user_memory:rejected",), result.tool_outcomes)
            self.assertEqual({}, store.read("u001")["facts"])


if __name__ == "__main__":
    unittest.main()
