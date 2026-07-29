"""Conservative extraction of explicit user-authored durable memory updates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExplicitMemoryUpdate:
    name_and_nickname: dict[str, str]
    profession: str | None
    preferences: dict[str, str]
    current_activities: list[str]
    other_facts: dict[str, str]
    preference_opt_in: bool

    @property
    def facts(self) -> dict[str, str]:
        """Legacy projection retained for callers from the JSON profile."""

        result: dict[str, str] = {}
        if "name" in self.name_and_nickname:
            result["name"] = self.name_and_nickname["name"]
        if "nickname" in self.name_and_nickname:
            result["preferred_name"] = self.name_and_nickname["nickname"]
        if self.profession:
            result["profession"] = self.profession
        result.update(self.other_facts)
        return result

    @property
    def fields(self) -> tuple[str, ...]:
        fields = [*self.name_and_nickname.keys()]
        if self.profession:
            fields.append("profession")
        fields.extend(self.preferences.keys())
        if self.current_activities:
            fields.append("current_activities")
        fields.extend(self.other_facts.keys())
        return tuple(fields)

    @property
    def empty(self) -> bool:
        return not (
            self.name_and_nickname
            or self.profession
            or self.preferences
            or self.current_activities
            or self.other_facts
        )


_PREFIX = re.compile(
    r"^\s*(?:please\s+)?(?:remember|save|store)\s+(?:that\s+)?",
    re.IGNORECASE,
)
# The patterns match a complete user message after the optional explicit
# remember/save/store prefix. They intentionally do not inspect assistant
# output, retrieved documents, or conversation history.
_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("name", "nickname", r"my\s+(?:preferred\s+name|nickname)\s+is\s+(.+)$"),
    ("name", "name", r"my\s+(?:full\s+)?name\s+is\s+(.+)$"),
    ("profession", "profession", r"my\s+profession\s+is\s+(.+)$"),
    ("profession", "profession", r"i\s+(?:work|am\s+working)\s+as\s+(.+)$"),
    ("preference", "language", r"my\s+(?:preferred\s+)?language\s+is\s+(.+)$"),
    ("preference", "response_style", r"(?:my\s+response\s+style\s+is|i\s+prefer)\s+(.+?)\s+responses?$"),
    ("preference", "date_format", r"my\s+date\s+format\s+is\s+(.+)$"),
    (
        "preference",
        "communication_channel",
        r"my\s+(?:preferred\s+)?communication\s+channel\s+is\s+(.+)$",
    ),
    ("other", "working_timezone", r"my\s+(?:working\s+)?timezone\s+is\s+(.+)$"),
    ("other", "office_location", r"my\s+office\s+location\s+is\s+(.+)$"),
    ("activity", "current_activities", r"(?:my\s+current\s+activity\s+is|i(?:\s+am|['’]m)\s+currently\s+working\s+on)\s+(.+)$"),
)


def extract_explicit_memory_update(message: Any, *, preference_opt_in: bool = False) -> ExplicitMemoryUpdate | None:
    """Recognize only an explicit user statement of a durable value.

    A leading ``remember``, ``save``, or ``store`` is accepted, but is not
    required for direct declarative statements such as ``My nickname is
    Davis``. This is still conservative: every supported shape is a complete
    user message and values are validated again by the Markdown store.
    """

    if not isinstance(message, str):
        return None
    remainder = _PREFIX.sub("", message, count=1).strip().rstrip(".")
    # A prefix must actually have matched when it is present; arbitrary
    # assistant-style prose is never passed here by the service, but requiring
    # one of these exact shapes keeps extraction deterministic.
    for group, field, pattern in _PATTERNS:
        value_match = re.fullmatch(pattern, remainder, flags=re.IGNORECASE)
        if not value_match:
            continue
        value = value_match.group(1).strip().strip('"“”\'')
        if not value:
            return None
        names: dict[str, str] = {}
        profession: str | None = None
        preferences: dict[str, str] = {}
        activities: list[str] = []
        other: dict[str, str] = {}
        if group == "name":
            names[field] = value
        elif group == "profession":
            profession = value
        elif group == "preference":
            preferences[field] = value
        elif group == "activity":
            activities = [value]
        else:
            other[field] = value
        return ExplicitMemoryUpdate(
            name_and_nickname=names,
            profession=profession,
            preferences=preferences,
            current_activities=activities,
            other_facts=other,
            # An explicit declaration is the required user opt-in for a
            # preference. The caller cannot use this extractor for a document
            # or assistant-generated string.
            preference_opt_in=True,
        )
    return None


__all__ = ["ExplicitMemoryUpdate", "extract_explicit_memory_update"]
