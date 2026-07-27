"""Deterministic routing helpers for the main orchestrator graph."""

from __future__ import annotations

from app.agents.orchestrator.action_routing import wants_ticket_creation
from app.agents.orchestrator.state import RouteName


STRUCTURED_TERMS = (
    "ticket",
    "case",
    "holiday",
    "budget",
    "revenue risk",
    "vendor",
    "headcount",
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
    """Choose graph route using deterministic, testable rules."""

    lowered = message.lower()
    if wants_ticket_creation(message):
        return "ticket_create"
    has_structured = any(term in lowered for term in STRUCTURED_TERMS)
    has_rag = any(term in lowered for term in RAG_TERMS)
    asks_two_things = " and " in lowered or " also " in lowered

    if has_structured and (has_rag or asks_two_things):
        return "combined"
    if has_structured:
        return "sql"
    return "rag"
