"""Conservative extraction for explicit, user-requested memory updates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExplicitMemoryUpdate:
    facts: dict[str, str]
    preferences: dict[str, str]
    preference_opt_in: bool

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple([*self.facts.keys(), *self.preferences.keys()])

    @property
    def empty(self) -> bool:
        return not self.facts and not self.preferences


_PREFIX = re.compile(
    r"^\s*(?:please\s+)?(?:remember|save|store)\s+(?:that\s+)?",
    re.IGNORECASE,
)
_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("fact", "preferred_name", r"my\s+preferred\s+name\s+is\s+(.+)$"),
    ("fact", "working_timezone", r"my\s+(?:working\s+)?timezone\s+is\s+(.+)$"),
    ("fact", "office_location", r"my\s+office\s+location\s+is\s+(.+)$"),
    ("preference", "language", r"my\s+(?:preferred\s+)?language\s+is\s+(.+)$"),
    ("preference", "response_style", r"(?:my\s+response\s+style\s+is|i\s+prefer)\s+(.+?)\s+responses?$"),
    ("preference", "date_format", r"my\s+date\s+format\s+is\s+(.+)$"),
    (
        "preference",
        "communication_channel",
        r"my\s+(?:preferred\s+)?communication\s+channel\s+is\s+(.+)$",
    ),
)


def extract_explicit_memory_update(message: Any, *, preference_opt_in: bool = False) -> ExplicitMemoryUpdate | None:
    """Recognize only an explicit remember/save/store instruction.

    No inference from ordinary conversation is performed. Values are still
    validated by ``JSONUserMemoryStore``; this function only identifies the
    narrow user-authored shape and never writes anything itself.
    """

    if not isinstance(message, str):
        return None
    match = _PREFIX.match(message)
    if not match:
        return None
    remainder = message[match.end() :].strip().rstrip(".")
    for group, field, pattern in _PATTERNS:
        value_match = re.fullmatch(pattern, remainder, flags=re.IGNORECASE)
        if value_match:
            value = value_match.group(1).strip()
            if not value:
                return None
            if group == "fact":
                return ExplicitMemoryUpdate({field: value}, {}, preference_opt_in=True)
            return ExplicitMemoryUpdate({}, {field: value}, preference_opt_in=True or preference_opt_in)
    return None


__all__ = ["ExplicitMemoryUpdate", "extract_explicit_memory_update"]
