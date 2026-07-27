"""Deterministic helpers for conversational and general-knowledge routes."""

from __future__ import annotations

import re


def casual_intent(message: str) -> str | None:
    """Return a casual intent only for short, conversation-only messages.

    The token allowlists make this tolerant of punctuation, capitalization, and
    common polite modifiers without turning a substantive request into CASUAL.
    """

    normalized = _normalize(message)
    if not normalized:
        return None
    tokens = normalized.split()

    patterns: tuple[str, frozenset[str], str] = (
        (
            "how are you",
            frozenset({"how", "are", "you", "doing", "today", "going"}),
            "how_are_you",
        ),
        (
            "greeting",
            frozenset({"hi", "hello", "hey", "there", "good", "morning", "afternoon", "evening"}),
            "greeting",
        ),
        (
            "thanks",
            frozenset({"thanks", "thank", "you", "so", "much", "very", "a", "lot"}),
            "thanks",
        ),
        (
            "welcome",
            frozenset({"you", "are", "re", "welcome", "no", "problem", "pleasure", "of", "course"}),
            "welcome",
        ),
        (
            "goodbye",
            frozenset({"bye", "goodbye", "see", "you", "later", "soon", "take", "care"}),
            "goodbye",
        ),
    )
    for pattern, allowed_tokens, intent in patterns:
        if normalized == pattern or (set(tokens).issubset(allowed_tokens) and _matches_casual_shape(tokens, intent)):
            return intent
    return None


def casual_response(message: str) -> str | None:
    """Return a natural deterministic response for a casual message."""

    responses = {
        "greeting": "Hi! How can I help you today?",
        "how_are_you": "I'm doing well, thanks for asking! How can I help you today?",
        "thanks": "You're welcome! Let me know if you need anything else.",
        "welcome": "Of course! Let me know if you need anything else.",
        "goodbye": "Goodbye! Have a great day.",
    }
    intent = casual_intent(message)
    return responses.get(intent) if intent else None


def is_general_knowledge_question(message: str) -> bool:
    """Identify educational, non-NexusOne questions without exact matching."""

    lowered = _normalize(message)
    if not lowered or casual_intent(lowered):
        return False
    if _has_internal_reference(lowered):
        return False
    if any(term in lowered for term in _GENERAL_TOPICS):
        return True
    return bool(
        re.search(
            r"\b(what is|what are|explain|define|how does|how do .* work|why does|difference between)\b",
            lowered,
        )
    )


def build_local_general_answer(question: str) -> str | None:
    """Answer a small, explicit local general-knowledge set.

    Returning ``None`` for an unsupported topic is intentional: callers can
    expose the existing capability fallback instead of fabricating facts.
    """

    lowered = _normalize(question)
    if "machine learning" in lowered:
        return (
            "Machine learning is a way to build software that learns patterns from examples and uses those patterns "
            "to make predictions or decisions, rather than relying only on hand-written rules."
        )
    if "rest api" in lowered or "restful api" in lowered:
        return (
            "A REST API is a web interface that models data as resources and uses standard HTTP methods such as GET, "
            "POST, PUT, and DELETE to read or change those resources."
        )
    if "docker" in lowered:
        return (
            "Docker packages an application and its dependencies into a container image so it can run in a more "
            "consistent, isolated environment across development, testing, and deployment."
        )
    if "vector database" in lowered or "vector db" in lowered:
        return (
            "A vector database stores numerical embeddings and searches for nearby vectors. It is commonly used to "
            "find semantically similar items, such as documents related to a question."
        )
    if re.search(r"\btcp\b", lowered):
        return (
            "TCP is a connection-oriented transport protocol. It establishes a connection, numbers and acknowledges "
            "data, retransmits missing pieces, and controls the sending rate so an ordered byte stream arrives reliably."
        )
    if "vacation policy" in lowered and any(marker in lowered for marker in ("typical", "generally", "usually")):
        return (
            "A typical vacation policy explains how time off is accrued or granted, how employees request it, "
            "which approval rules apply, and how holidays or carryover are handled. Exact rules vary by employer."
        )
    return None


_GENERAL_TOPICS = (
    "machine learning",
    "rest api",
    "restful api",
    "docker",
    "vector database",
    "vector db",
    "tcp",
)


def _normalize(message: str) -> str:
    normalized = message.lower().replace("’", "'")
    normalized = re.sub(r"\byou're\b", "you are", normalized)
    normalized = re.sub(r"\bhow's\b", "how is", normalized)
    normalized = re.sub(r"[^a-z0-9']+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _matches_casual_shape(tokens: list[str], intent: str) -> bool:
    if intent == "greeting":
        return len(tokens) <= 4 and any(token in tokens for token in ("hi", "hello", "hey", "good"))
    if intent == "how_are_you":
        return len(tokens) <= 6 and tokens[:3] == ["how", "are", "you"]
    if intent == "thanks":
        return len(tokens) <= 6 and ("thanks" in tokens or tokens[:2] == ["thank", "you"])
    if intent == "welcome":
        return len(tokens) <= 5 and ("welcome" in tokens or "pleasure" in tokens or "problem" in tokens)
    if intent == "goodbye":
        return len(tokens) <= 5 and any(token in tokens for token in ("bye", "goodbye", "later"))
    return False


def _has_internal_reference(lowered: str) -> bool:
    return bool(
        re.search(r"\b(our|company|internal|nexusone|employee|engineering|department|team)\b", lowered)
        or "company's" in lowered
    )
