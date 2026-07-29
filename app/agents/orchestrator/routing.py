"""Route contract for validated classifier results.

This module deliberately contains no message-pattern classifier.  Intent
classification belongs to :mod:`intent_classifier`; this layer only maps a
validated finite label to an existing safe graph route.
"""

from __future__ import annotations

from app.agents.orchestrator.intent_classifier import IntentClassificationResult
from app.agents.orchestrator.state import RouteName


_INTENT_TO_ROUTE: dict[str, RouteName] = {
    "casual": "CASUAL",
    "general_question": "GENERAL_KNOWLEDGE",
    "knowledge_lookup": "rag",
    "ticket_guidance": "ticket_guidance",
    "structured_lookup": "sql",
    "combined_lookup": "combined",
    "ticket_create": "ticket_create",
    "ticket_status": "sql",
    # Conversation history is not persisted in this branch.  It must not be
    # guessed as SQL or retrieved from unrelated documents.
    "history_lookup": "unsupported",
    "feedback": "feedback",
    "clarification": "clarification",
    "unsupported": "unsupported",
}


def route_from_intent(result: IntentClassificationResult) -> RouteName:
    """Map a classifier contract to a graph route without granting authority."""

    if result.needs_clarification and result.intent not in {"ticket_create", "clarification"}:
        return "clarification"
    return _INTENT_TO_ROUTE.get(result.intent, "clarification")


__all__ = ["route_from_intent"]
