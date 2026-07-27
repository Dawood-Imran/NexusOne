"""Deterministic routing helpers for the main orchestrator graph."""

from __future__ import annotations

import re

from app.agents.orchestrator.action_routing import wants_ticket_creation
from app.agents.orchestrator.knowledge import casual_intent, is_general_knowledge_question
from app.agents.orchestrator.state import RouteName


STRUCTURED_TERMS = (
    "ticket",
    "case",
    "holiday",
    "budget",
    "revenue risk",
    "vendor",
    "headcount",
    "how many employees",
    "project status",
    "employee directory",
)

RAG_TERMS = (
    "policy",
    "process",
    "procedure",
    "guideline",
    "guide",
    "how do",
    "how can",
    "request",
    "access",
    "leave",
    "benefit",
    "onboarding",
    "runbook",
    "document",
    "docs",
)


def route_message(message: str) -> RouteName:
    """Choose a safe route with deterministic, testable rules.

    This classifier runs only after the graph's guardrail precheck. Internal
    references win over general-knowledge heuristics, while exact structured
    questions retain their SQL route.
    """

    lowered = message.lower()
    if wants_ticket_creation(message):
        return "ticket_create"
    if casual_intent(message):
        return "CASUAL"

    has_structured = any(_contains_term(lowered, term) for term in STRUCTURED_TERMS)
    has_rag = any(_contains_term(lowered, term) for term in RAG_TERMS)
    asks_two_things = " and " in lowered or " also " in lowered

    # Educational questions about NexusOne need approved internal context,
    # rather than an external/general answer. Exact headcount and similar
    # requests remain SQL even when they mention the company.
    internal_knowledge = _looks_internal_knowledge_question(lowered)
    if internal_knowledge and not _is_exact_structured_question(lowered):
        return "rag"
    if has_structured and (has_rag or asks_two_things):
        return "combined"
    if has_structured:
        return "sql"
    if is_general_knowledge_question(message) and (
        not has_rag or any(marker in lowered for marker in ("typical", "generally", "usually"))
    ):
        return "GENERAL_KNOWLEDGE"
    return "rag"


def _contains_term(text: str, term: str) -> bool:
    # Preserve the existing substring-friendly vocabulary (for example,
    # ``holiday`` should match ``holidays``) while keeping ``how do`` from
    # matching the distinct phrase ``how does``.
    if term in {"how do", "how can"}:
        return bool(re.search(rf"\b{re.escape(term)}\b", text))
    return term in text


def _looks_internal_knowledge_question(lowered: str) -> bool:
    internal_reference = any(
        marker in lowered
        for marker in ("nexusone", "our company", "our company's", "company's", "internal")
    )
    return internal_reference and any(
        marker in lowered
        for marker in ("policy", "process", "procedure", "system", "how does", "how do", "explain")
    )


def _is_exact_structured_question(lowered: str) -> bool:
    return any(
        marker in lowered
        for marker in ("headcount", "how many employees", "employee directory", "holidays apply", "budget utilization")
    )
