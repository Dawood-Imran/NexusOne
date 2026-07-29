"""Deterministic helpers for conversational and general-knowledge routes."""

from __future__ import annotations

import re
from typing import Any


NO_APPROVED_TICKET_GUIDANCE_MESSAGE = (
    "No approved reference is available for that ticket guidance, so I will not guess department or category rules. "
    "If you want to take the supported next step, explicitly ask me to create or submit a ticket; I will ask for "
    "any required details before writing anything."
)


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


def retained_ticket_guidance_results(
    results: tuple[Any, ...],
    *,
    threshold: float,
) -> tuple[Any, ...]:
    """Keep only above-threshold results with safe usable source content."""

    retained: list[Any] = []
    for result in results:
        try:
            score = float(getattr(result, "score", 0.0))
        except (TypeError, ValueError):
            continue
        if score < threshold:
            continue
        if _safe_guidance_paragraphs(_source_text_for_result(result)):
            retained.append(result)
    return tuple(retained)


def build_ticket_guidance_answer(
    results: tuple[Any, ...],
    *,
    threshold: float,
) -> str:
    """Compose ticket guidance only from retained, authorized source chunks.

    Guidance is a process answer, not an action.  The source text is filtered
    for instruction-like paragraphs before it is shown, so a malicious passage
    in an otherwise approved document cannot become an instruction to the
    assistant.  The caller uses the same threshold when constructing citations.
    """

    retained = retained_ticket_guidance_results(results, threshold=threshold)
    if not retained:
        return NO_APPROVED_TICKET_GUIDANCE_MESSAGE

    blocks: list[str] = []
    for index, result in enumerate(retained, start=1):
        chunk = getattr(result, "chunk", None)
        document = getattr(result, "document", None)
        title = getattr(chunk, "title", None) or getattr(document, "title", None) or "Approved ticket guidance"
        paragraphs = _safe_guidance_paragraphs(_source_text_for_result(result))
        if not paragraphs:
            continue
        blocks.append(f"Approved guidance from {title} [{index}]:\n" + "\n\n".join(paragraphs))

    if not blocks:
        return NO_APPROVED_TICKET_GUIDANCE_MESSAGE
    return "Here is the approved ticket guidance:\n\n" + "\n\n".join(blocks)[:6_000]


def sanitize_ticket_guidance_source_text(text: str) -> str:
    """Remove instruction-like paragraphs before guidance citations are shown."""

    return "\n\n".join(_safe_guidance_paragraphs(text))[:6_000]


def _source_text_for_result(result: Any) -> str:
    chunk = getattr(result, "chunk", None)
    document = getattr(result, "document", None)
    return str(getattr(chunk, "text", None) or getattr(document, "body", None) or getattr(result, "snippet", ""))


def build_local_general_answer(question: str) -> str | None:
    """Answer a small, explicit local general-knowledge set.

    Returning ``None`` for an unsupported topic is intentional: callers can
    expose the existing capability fallback instead of fabricating facts.
    """

    lowered = _normalize(question)
    if "create a ticket" in lowered and any(
        marker in lowered
        for marker in ("i can create", "please provide", "what information", "which team", "what category")
    ):
        return (
            "To create a ticket, explicitly ask me to create or submit it. Then provide the team "
            "(IT, HR, or Admin), the category, and a short description."
        )
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


_SOURCE_INSTRUCTION_PATTERN = re.compile(
    r"(?:ignore|disregard|override|bypass)\s+(?:all\s+|previous\s+|the\s+)?"
    r"(?:instructions?|rules?|guardrails?)|"
    r"(?:reveal|dump|expose)\s+(?:the\s+)?(?:hidden|secret|system|private)",
    re.IGNORECASE,
)


def _safe_guidance_paragraphs(text: str) -> list[str]:
    paragraphs: list[str] = []
    for paragraph in re.split(r"\n\s*\n", text):
        stripped = paragraph.strip()
        if not stripped:
            continue
        if re.match(r"^#+\s*Related Sources\b", stripped, flags=re.IGNORECASE):
            break
        if _SOURCE_INSTRUCTION_PATTERN.search(stripped):
            continue
        paragraphs.append(re.sub(r"^#+\s*", "", stripped.replace("`", ""), flags=re.MULTILINE).strip())
    return paragraphs


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
