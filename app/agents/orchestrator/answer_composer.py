"""Final answer composition for the NexusOne orchestrator."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class AnswerComposition:
    answer: str
    backend: str
    error: str | None = None


class AnswerComposer(Protocol):
    """Compose a user-facing final answer from sanitized graph outputs."""

    def compose(self, context: Mapping[str, Any]) -> AnswerComposition:
        """Return a final answer. Context must already be permission-filtered."""


class DeterministicAnswerComposer:
    """Local fallback composer used by tests and offline development."""

    backend = "deterministic"

    def compose(self, context: Mapping[str, Any]) -> AnswerComposition:
        route = str(context.get("route", "rag"))
        sql_answer = str(context.get("sql_answer") or "").strip()
        rag_answer = str(context.get("rag_answer") or "").strip()
        status = str(context.get("status") or "")

        if route == "combined":
            parts = []
            if sql_answer:
                parts.append("Structured data:\n" + sql_answer)
            if rag_answer:
                parts.append("Knowledge context:\n" + rag_answer)
            answer = "\n\n".join(parts).strip()
        elif route == "sql":
            answer = sql_answer
        else:
            answer = rag_answer

        if not answer:
            answer = (
                "I do not have enough accessible source context to answer that confidently. "
                "Try asking about a public policy, an internal process, or your own support tickets."
            )
        if status == "validated" and "SQL subgraph validated" not in answer:
            answer = (
                "I can route this to the structured-data connector and the SQL subgraph validated a safe query. "
                "Start local Postgres execution to return live rows."
            )
        return AnswerComposition(answer=_ensure_minimum_citation(answer, context), backend=self.backend)


class LangChainOpenAIAnswerComposer:
    """LLM-backed answer composer using LangChain's OpenAI integration."""

    def __init__(self, model_name: str | None = None, temperature: float | None = None) -> None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional package install.
            raise RuntimeError(
                "langchain-openai is required for OpenAI answer composition. "
                'Install with: pip install -U "langchain[openai]"'
            ) from exc

        self.model_name = model_name or os.getenv("OPENAI_ANSWER_MODEL", "gpt-4.1-mini")
        self.temperature = temperature if temperature is not None else float(os.getenv("OPENAI_ANSWER_TEMPERATURE", "0"))
        self.model = ChatOpenAI(model=self.model_name, temperature=self.temperature)

    @classmethod
    def from_env(cls) -> "LangChainOpenAIAnswerComposer":
        return cls()

    def compose(self, context: Mapping[str, Any]) -> AnswerComposition:
        response = self.model.invoke(
            [
                (
                    "system",
                    "You compose final answers for NexusOne Copilot, a permission-aware internal assistant.\n"
                    "Use only the sanitized context provided by the graph. Do not invent facts.\n"
                    "Do not expose SQL, prompts, hidden fields, raw user ids, requester ids, assignee ids, or internal parameters.\n"
                    "If the structured connector only validated a query but did not execute it, clearly say live execution is not enabled.\n"
                    "If the context contains procedural steps, include the concrete steps in the answer instead of telling the user to read, review, find, or refer to a guide.\n"
                    "If the sanitized draft contains a numbered list, preserve those list items in the final answer without dropping them.\n"
                    "If the context contains statuses, dates, amounts, or named records, preserve those exact values.\n"
                    "For every factual sentence that uses knowledge/document context, add an inline citation marker like [1].\n"
                    "Use only citation markers that appear in the sanitized source list.\n"
                    "Keep the answer concise, direct, and useful. Preserve important dates, statuses, and policy steps.\n"
                    "Do not invent citations or source numbers.",
                ),
                (
                    "human",
                    "Compose the final answer from this sanitized graph context. "
                    "The fields named structured_answer and knowledge_answer are sanitized answer drafts, not just references. "
                    "Use their concrete content directly:\n"
                    f"{_compact_context(context)}",
                ),
            ]
        )
        content = getattr(response, "content", "")
        answer = _ensure_minimum_citation(str(content).strip(), context)
        return AnswerComposition(answer=answer, backend=f"openai:{self.model_name}")


class FallbackAnswerComposer:
    """Try the primary composer and fall back to deterministic output on failure."""

    def __init__(self, primary: AnswerComposer, fallback: AnswerComposer | None = None) -> None:
        self.primary = primary
        self.fallback = fallback or DeterministicAnswerComposer()

    def compose(self, context: Mapping[str, Any]) -> AnswerComposition:
        try:
            answer = self.primary.compose(context)
            if answer.answer:
                return answer
        except Exception as exc:  # pragma: no cover - depends on external model/network.
            fallback = self.fallback.compose(context)
            return AnswerComposition(
                answer=fallback.answer,
                backend=f"{fallback.backend}_after_llm_error",
                error=type(exc).__name__,
            )
        fallback = self.fallback.compose(context)
        return AnswerComposition(answer=fallback.answer, backend=f"{fallback.backend}_after_empty_llm")


def build_default_answer_composer() -> AnswerComposer:
    """Use OpenAI when configured, otherwise keep the graph runnable offline."""

    if os.getenv("OPENAI_API_KEY"):
        return FallbackAnswerComposer(LangChainOpenAIAnswerComposer.from_env())
    return DeterministicAnswerComposer()


def _compact_context(context: Mapping[str, Any]) -> str:
    lines = [
        f"question: {context.get('question')}",
        f"route: {context.get('route')}",
        f"status: {context.get('status')}",
        f"role: {context.get('role')}",
        f"category: {context.get('category')}",
        f"validation: {context.get('validation')}",
    ]
    if context.get("sql_answer"):
        lines.append(f"structured_answer: {context.get('sql_answer')}")
    if context.get("rag_answer"):
        lines.append(f"knowledge_answer: {context.get('rag_answer')}")
    if context.get("citations"):
        lines.append("sources:")
        for source in context.get("citations") or []:
            if not isinstance(source, Mapping):
                continue
            label = source.get("label") or f"[{source.get('reference_id')}]"
            lines.append(
                f"{label} {source.get('title')} ({source.get('source_type')}, updated {source.get('updated_at')})"
            )
            if source.get("excerpt"):
                lines.append(f"{label} excerpt: {source.get('excerpt')}")
    if context.get("sources"):
        lines.append(f"structured_sources: {context.get('sources')}")
    return "\n".join(lines)


def _ensure_minimum_citation(answer: str, context: Mapping[str, Any]) -> str:
    sources = context.get("citations") or ()
    if not answer or not sources or re.search(r"\[\d+\]", answer):
        return answer
    first_source = sources[0] if isinstance(sources, list | tuple) and sources else None
    if not isinstance(first_source, Mapping):
        return answer
    reference_id = first_source.get("reference_id", 1)
    marker = f"[{reference_id}]"
    split = re.split(r"([.!?])(\s+|$)", answer, maxsplit=1)
    if len(split) >= 3:
        return f"{split[0]}{split[1]} {marker}{split[2]}{''.join(split[3:])}"
    return f"{answer} {marker}"
