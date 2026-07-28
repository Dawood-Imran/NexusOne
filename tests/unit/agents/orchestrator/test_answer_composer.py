import unittest

from app.agents.orchestrator.answer_composer import (
    AnswerComposition,
    DeterministicAnswerComposer,
    FallbackAnswerComposer,
    LangChainOpenAIAnswerComposer,
)


class _Chunk:
    def __init__(self, content: str) -> None:
        self.content = content


class _StreamingModel:
    def __init__(self, chunks: list[str], error: Exception | None = None) -> None:
        self.chunks = chunks
        self.error = error

    def stream(self, messages):
        if self.error is not None:
            raise self.error
        yield from (_Chunk(chunk) for chunk in self.chunks)


class AnswerComposerStreamingTest(unittest.TestCase):
    def test_openai_stream_adds_required_citation_as_a_final_delta(self) -> None:
        composer = object.__new__(LangChainOpenAIAnswerComposer)
        composer.model = _StreamingModel(["A useful", " answer."])
        composer.model_name = "fixture-model"
        deltas: list[str] = []

        result = composer.stream(
            {"route": "rag", "citations": [{"reference_id": 1}]},
            deltas.append,
        )

        self.assertEqual("A useful answer. [1]", result.answer)
        self.assertEqual(result.answer, "".join(deltas))
        self.assertEqual("openai:fixture-model", result.backend)

    def test_fallback_stream_handles_provider_error_without_leaking_exception_text(self) -> None:
        primary = object.__new__(LangChainOpenAIAnswerComposer)
        primary.model = _StreamingModel([], RuntimeError("secret prompt and token"))
        primary.model_name = "fixture-model"
        composer = FallbackAnswerComposer(primary, DeterministicAnswerComposer())
        deltas: list[str] = []
        errors: list[str] = []

        result = composer.stream(
            {"route": "rag", "rag_answer": "Approved local answer."},
            deltas.append,
            errors.append,
        )

        self.assertTrue(result.answer)
        self.assertEqual(result.answer, "".join(deltas))
        self.assertEqual(1, len(errors))
        self.assertNotIn("secret", errors[0].lower())
        self.assertNotIn("token", errors[0].lower())
        self.assertIn("after_llm_error", result.backend)

    def test_no_reference_context_is_safe_and_does_not_invent_a_citation(self) -> None:
        composer = DeterministicAnswerComposer()

        result = composer.compose(
            {
                "route": "rag",
                "status": "no_answer",
                "reference_status": "none_reached_threshold",
                "rag_answer": "Below-threshold source must not be used.",
                "citations": [],
            }
        )

        self.assertEqual("deterministic", result.backend)
        self.assertIn("No sufficiently relevant reference found", result.answer)
        self.assertNotIn("Below-threshold", result.answer)
        self.assertNotRegex(result.answer, r"\[\d+\]")

    def test_invalid_provider_citation_is_removed_and_retained_source_is_used(self) -> None:
        composer = object.__new__(LangChainOpenAIAnswerComposer)
        composer.model = type(
            "Model",
            (),
            {"invoke": lambda _self, _messages: _Chunk("A grounded answer [2].")},
        )()
        composer.model_name = "fixture-model"

        result = composer.compose(
            {
                "route": "rag",
                "citations": [{"reference_id": 1}],
            }
        )

        self.assertEqual("A grounded answer. [1]", result.answer)
        self.assertNotIn("[2]", result.answer)

    def test_deterministic_stream_matches_non_streaming_contract(self) -> None:
        composer = DeterministicAnswerComposer()
        context = {"route": "rag", "rag_answer": "One\nTwo"}
        deltas: list[str] = []

        streamed = composer.stream(context, deltas.append)
        normal = composer.compose(context)

        self.assertEqual(normal, streamed)
        self.assertEqual(normal.answer, "".join(deltas))


if __name__ == "__main__":
    unittest.main()
