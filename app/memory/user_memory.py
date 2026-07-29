"""Validated, server-owned long-term user memory in Markdown profiles.

The public store API intentionally accepts only a validated authenticated
manifest ID.  Model-facing callers use :mod:`app.memory.tools`, whose tool
closures capture that identity from the server runtime context and expose no
user/path selector.
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.auth.profiles import get_profile


MEMORY_SCHEMA_VERSION = 2
MAX_MEMORY_FIELDS = 8
MAX_VALUE_CHARS = 120
MAX_PREFERRED_NAME_CHARS = 80
MAX_ACTIVITY_ITEMS = 5
_SAFE_USER_ID = re.compile(r"^u[0-9]{3}$")
_SAFE_FIELD = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_SENSITIVE_FIELD = re.compile(
    r"(password|passwd|secret|token|api[_ -]?key|credential|ssn|social|salary|bank|card|medical|health|diagnos|passport|tax|private[_ -]?key)",
    re.IGNORECASE,
)
_INSTRUCTION_MARKERS = (
    "sk-",
    "bearer ",
    "password=",
    "token=",
    "ignore previous",
    "ignore all previous",
    "ignore ",
    "system prompt",
    "reveal hidden",
    "follow these instructions",
    "developer message",
    "api key",
    "api_key",
    "credential",
    "password",
    "secret",
    "ssn",
    "bank account",
)
_NAME_FIELDS = frozenset({"name", "nickname", "preferred_name"})
_PREFERENCE_FIELDS = frozenset(
    {
        "language",
        "response_style",
        "date_format",
        "communication_channel",
        "theme",
        "notification_style",
        "food_preference",
        "drink_preference",
    }
)
_OTHER_FACT_FIELDS = frozenset(
    {
        "working_timezone",
        "office_location",
        "team",
        "hobby",
        "pronouns",
        "favorite_color",
        "favorite_food",
    }
)
_ALLOWED_RESPONSE_STYLES = frozenset({"concise", "balanced", "detailed"})
_ALLOWED_DATE_FORMATS = frozenset({"iso", "day_first", "month_first"})
_ALLOWED_CHANNELS = frozenset({"email", "chat", "slack"})
_ALLOWED_NOTIFICATION_STYLES = frozenset({"minimal", "normal", "all"})


class MemoryValidationError(ValueError):
    """A user memory update failed the bounded safe schema."""


class UserMemoryStore(Protocol):
    def read(self, user_id: str) -> dict[str, Any]: ...

    def update(
        self,
        user_id: str,
        *,
        name_and_nickname: Mapping[str, Any] | None = None,
        profession: str | None = None,
        preferences: Mapping[str, Any] | None = None,
        current_activities: Sequence[Any] | str | None = None,
        other_facts: Mapping[str, Any] | None = None,
        # Legacy aliases are retained for callers from the previous JSON
        # implementation. They are normalized into the Markdown sections.
        facts: Mapping[str, Any] | None = None,
        source: str = "explicit_user",
        preference_opt_in: bool = False,
    ) -> dict[str, Any]: ...


# Locks are process-wide so two store instances in the local server still
# serialize updates to the same profile. The advisory file lock also protects
# separate local worker processes.
_LOCKS: dict[Path, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class MarkdownUserMemoryStore:
    """File-backed per-user Markdown memory with atomic writes.

    ``JSONUserMemoryStore`` remains a source-compatible alias. New profiles are
    always ``<validated-user-id>.md`` files; no caller can supply a path or
    select another user's namespace.
    """

    def __init__(self, root_dir: str | Path, *, audit_path: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path = (
            Path(audit_path).expanduser().resolve()
            if audit_path
            else self.root_dir / "memory_audit.jsonl"
        )
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def read(self, user_id: str) -> dict[str, Any]:
        safe_user_id = _validated_user_id(user_id)
        path = self._profile_path(safe_user_id)
        lock = _lock_for(path)
        with lock, _file_lock(path.with_suffix(".lock")):
            payload = self._read_payload(path, safe_user_id)
        sanitized = _sanitized_payload(payload)
        self._audit(safe_user_id, "get_user_memory", "ok", tuple(_field_names(payload)))
        return sanitized

    def update(
        self,
        user_id: str,
        *,
        name_and_nickname: Mapping[str, Any] | None = None,
        profession: str | None = None,
        preferences: Mapping[str, Any] | None = None,
        current_activities: Sequence[Any] | str | None = None,
        other_facts: Mapping[str, Any] | None = None,
        facts: Mapping[str, Any] | None = None,
        source: str = "explicit_user",
        preference_opt_in: bool = False,
    ) -> dict[str, Any]:
        safe_user_id = _validated_user_id(user_id)
        try:
            normalized_names = _normalize_name_section(name_and_nickname)
            normalized_preferences = _validate_mapping(
                preferences,
                allowed=_PREFERENCE_FIELDS,
                group="preferences",
            )
            normalized_other_facts = _validate_mapping(
                other_facts,
                allowed=_OTHER_FACT_FIELDS,
                group="other_facts",
            )
            normalized_profession = _validate_value(profession, "profession") if profession is not None else None
            normalized_activities = _normalize_activities(current_activities)
            legacy_names, legacy_profession, legacy_other = _normalize_legacy_facts(facts)
            normalized_names.update(legacy_names)
            normalized_profession = normalized_profession or legacy_profession
            normalized_other_facts.update(legacy_other)
        except MemoryValidationError:
            self._audit(
                safe_user_id,
                "update_user_memory",
                "rejected",
                _input_field_names(name_and_nickname, preferences, other_facts, facts),
            )
            raise

        if normalized_preferences and not preference_opt_in:
            self._audit(
                safe_user_id,
                "update_user_memory",
                "preference_opt_in_required",
                tuple(normalized_preferences),
            )
            raise MemoryValidationError("explicit preference opt-in is required")
        if (
            not normalized_names
            and normalized_profession is None
            and not normalized_preferences
            and normalized_activities is None
            and not normalized_other_facts
        ):
            raise MemoryValidationError("at least one supported memory field is required")

        safe_source = _safe_source(source)
        path = self._profile_path(safe_user_id)
        lock = _lock_for(path)
        with lock, _file_lock(path.with_suffix(".lock")):
            payload = self._read_payload(path, safe_user_id)
            now = _now()
            sections = payload["sections"]
            _merge_entries(sections["name_and_nickname"], normalized_names, safe_source, now)
            if normalized_profession is not None:
                sections["profession"] = _entry(normalized_profession, safe_source, now)
            _merge_entries(sections["preferences"], normalized_preferences, safe_source, now)
            if normalized_activities is not None:
                sections["current_activities"] = [
                    _entry(value, safe_source, now) for value in normalized_activities
                ]
            _merge_entries(sections["other_facts"], normalized_other_facts, safe_source, now)
            if _entry_count(sections) > MAX_MEMORY_FIELDS:
                self._audit(
                    safe_user_id,
                    "update_user_memory",
                    "rejected_too_many_fields",
                    _field_names(payload),
                )
                raise MemoryValidationError("profile memory is full; update fewer fields")
            payload["schema_version"] = MEMORY_SCHEMA_VERSION
            payload["user_id"] = safe_user_id
            payload["updated_at"] = now
            self._atomic_write(path, payload)

        changed_fields = tuple(
            [
                *normalized_names.keys(),
                *( ["profession"] if normalized_profession is not None else [] ),
                *normalized_preferences.keys(),
                *( ["current_activities"] if normalized_activities is not None else [] ),
                *normalized_other_facts.keys(),
            ][:MAX_MEMORY_FIELDS]
        )
        self._audit(safe_user_id, "update_user_memory", "ok", changed_fields)
        return _sanitized_payload(payload)

    def profile_path(self, user_id: str) -> Path:
        """Return the only safe profile path for a known authenticated user."""

        return self._profile_path(_validated_user_id(user_id))

    def _profile_path(self, user_id: str) -> Path:
        return self.root_dir / f"{user_id}.md"

    def _read_payload(self, path: Path, user_id: str) -> dict[str, Any]:
        if not path.exists():
            return _empty_payload(user_id)
        try:
            raw = _parse_markdown(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError, MemoryValidationError):
            self._audit(user_id, "get_user_memory", "invalid_file_reset", ())
            return _empty_payload(user_id)
        if raw.get("schema_version") != MEMORY_SCHEMA_VERSION:
            self._audit(user_id, "get_user_memory", "schema_reset", ())
            return _empty_payload(user_id)
        return _normalize_existing_payload(raw, user_id)

    def _atomic_write(self, path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        data = _render_markdown(payload)
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            try:
                directory_fd = os.open(path.parent, os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                # Directory fsync is not available on every local filesystem;
                # the atomic replace still prevents partial profile reads.
                pass
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _audit(self, user_id: str, action: str, outcome: str, fields: Sequence[str]) -> None:
        event = {
            "timestamp": _now(),
            "action": action,
            "user_id": user_id,
            "outcome": outcome,
            "fields": [str(field)[:48] for field in fields if isinstance(field, str)][:MAX_MEMORY_FIELDS],
        }
        lock = _lock_for(self.audit_path)
        with lock, _file_lock(self.audit_path.with_suffix(".lock")):
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def _validated_user_id(value: Any) -> str:
    profile = get_profile(value) if isinstance(value, str) else None
    if (
        not isinstance(value, str)
        or not _SAFE_USER_ID.fullmatch(value)
        or profile is None
        or profile.status != "active"
    ):
        raise MemoryValidationError("memory identity must be an authenticated NexusOne user")
    return value


def _normalize_name_section(values: Mapping[str, Any] | None) -> dict[str, str]:
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise MemoryValidationError("name_and_nickname must be an object")
    normalized: dict[str, str] = {}
    for field, value in values.items():
        canonical = "nickname" if field == "preferred_name" else field
        if canonical not in {"name", "nickname"}:
            raise MemoryValidationError("unsupported name or nickname field")
        normalized[canonical] = _validate_value(value, canonical)
    return normalized


def _validate_mapping(
    values: Mapping[str, Any] | None,
    *,
    allowed: frozenset[str],
    group: str,
) -> dict[str, str]:
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise MemoryValidationError(f"{group} must be an object")
    normalized: dict[str, str] = {}
    for field, value in values.items():
        if (
            not isinstance(field, str)
            or not field
            or not _SAFE_FIELD.fullmatch(field)
            or _SENSITIVE_FIELD.search(field)
            or field not in allowed
        ):
            raise MemoryValidationError("unsupported or sensitive memory field")
        normalized[field] = _validate_value(value, field)
    return normalized


def _normalize_legacy_facts(
    values: Mapping[str, Any] | None,
) -> tuple[dict[str, str], str | None, dict[str, str]]:
    if values is None:
        return {}, None, {}
    if not isinstance(values, Mapping):
        raise MemoryValidationError("facts must be an object")
    names: dict[str, str] = {}
    profession: str | None = None
    other: dict[str, str] = {}
    for field, value in values.items():
        if not isinstance(field, str):
            raise MemoryValidationError("unsupported memory field")
        if field in _NAME_FIELDS:
            names["nickname" if field == "preferred_name" else field] = _validate_value(value, field)
        elif field in _OTHER_FACT_FIELDS:
            other[field] = _validate_value(value, field)
        elif field == "profession":
            profession = _validate_value(value, field)
        else:
            raise MemoryValidationError("unsupported or sensitive memory field")
    return names, profession, other


def _normalize_activities(values: Sequence[Any] | str | None) -> list[str] | None:
    if values is None:
        return None
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, Sequence) or isinstance(values, (bytes, bytearray)):
        raise MemoryValidationError("current_activities must be a list of text")
    if not values or len(values) > MAX_ACTIVITY_ITEMS:
        raise MemoryValidationError("current_activities must contain one to five items")
    result = [_validate_value(item, "current_activity") for item in values]
    if len(set(item.casefold() for item in result)) != len(result):
        raise MemoryValidationError("current_activities must not contain duplicates")
    return result


def _validate_value(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise MemoryValidationError("memory values must be text")
    clean = re.sub(r"\s+", " ", value.replace("\x00", " ")).strip()
    maximum = MAX_PREFERRED_NAME_CHARS if field in {"name", "nickname", "preferred_name"} else MAX_VALUE_CHARS
    if not clean or len(clean) > maximum or "\n" in value or "\r" in value:
        raise MemoryValidationError("memory value is empty, too long, or contains a line break")
    lowered = clean.casefold()
    if _SENSITIVE_FIELD.search(field) or any(marker in lowered for marker in _INSTRUCTION_MARKERS):
        raise MemoryValidationError("sensitive or instruction-like values are not stored")
    if field == "response_style" and lowered not in _ALLOWED_RESPONSE_STYLES:
        raise MemoryValidationError("unsupported response style")
    if field == "date_format" and lowered not in _ALLOWED_DATE_FORMATS:
        raise MemoryValidationError("unsupported date format")
    if field == "communication_channel" and lowered not in _ALLOWED_CHANNELS:
        raise MemoryValidationError("unsupported communication channel")
    if field == "notification_style" and lowered not in _ALLOWED_NOTIFICATION_STYLES:
        raise MemoryValidationError("unsupported notification style")
    if field == "language" and not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,39}", clean):
        raise MemoryValidationError("unsupported language value")
    return clean


def _empty_payload(user_id: str) -> dict[str, Any]:
    now = _now()
    return {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "user_id": user_id,
        "created_at": now,
        "updated_at": now,
        "sections": {
            "name_and_nickname": {},
            "profession": None,
            "preferences": {},
            "current_activities": [],
            "other_facts": {},
        },
    }


def _normalize_existing_payload(raw: Mapping[str, Any], user_id: str) -> dict[str, Any]:
    result = _empty_payload(user_id)
    for key in ("created_at", "updated_at"):
        value = raw.get(key)
        if isinstance(value, str) and value and len(value) <= 64:
            result[key] = value
    sections = raw.get("sections")
    if not isinstance(sections, Mapping):
        return result
    try:
        result["sections"]["name_and_nickname"] = _normalize_existing_mapping(
            sections.get("name_and_nickname"), frozenset({"name", "nickname"})
        )
        profession = sections.get("profession")
        if isinstance(profession, Mapping):
            value = profession.get("value")
            if isinstance(value, str):
                result["sections"]["profession"] = _entry(
                    _validate_value(value, "profession"),
                    _safe_source(profession.get("source")),
                    _safe_timestamp(profession.get("updated_at")),
                )
        result["sections"]["preferences"] = _normalize_existing_mapping(
            sections.get("preferences"), _PREFERENCE_FIELDS
        )
        activities = sections.get("current_activities")
        if isinstance(activities, Sequence) and not isinstance(activities, (str, bytes, bytearray)):
            clean_activities: list[dict[str, str]] = []
            for item in list(activities)[:MAX_ACTIVITY_ITEMS]:
                if not isinstance(item, Mapping) or not isinstance(item.get("value"), str):
                    continue
                try:
                    clean_activities.append(
                        _entry(
                            _validate_value(item["value"], "current_activity"),
                            _safe_source(item.get("source")),
                            _safe_timestamp(item.get("updated_at")),
                        )
                    )
                except MemoryValidationError:
                    continue
            result["sections"]["current_activities"] = clean_activities
        result["sections"]["other_facts"] = _normalize_existing_mapping(
            sections.get("other_facts"), _OTHER_FACT_FIELDS
        )
    except MemoryValidationError:
        # Keep any valid independent sections but never allow a malformed file
        # to become model context or an authority source.
        return result
    if _entry_count(result["sections"]) > MAX_MEMORY_FIELDS:
        _trim_sections(result["sections"])
    return result


def _normalize_existing_mapping(value: Any, allowed: frozenset[str]) -> dict[str, dict[str, str]]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, dict[str, str]] = {}
    for field, item in list(value.items())[:MAX_MEMORY_FIELDS]:
        if field not in allowed or not isinstance(item, Mapping) or not isinstance(item.get("value"), str):
            continue
        try:
            result[field] = _entry(
                _validate_value(item["value"], field),
                _safe_source(item.get("source")),
                _safe_timestamp(item.get("updated_at")),
            )
        except MemoryValidationError:
            continue
    return result


def _parse_markdown(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        raise ValueError("missing profile front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("invalid profile front matter")
    metadata: dict[str, Any] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        if key not in {"schema_version", "user_id", "created_at", "updated_at"}:
            continue
        raw = raw.strip()
        try:
            metadata[key] = json.loads(raw)
        except json.JSONDecodeError:
            metadata[key] = raw.strip('"')
    if metadata.get("user_id") and not isinstance(metadata.get("user_id"), str):
        raise ValueError("invalid profile owner")
    sections = {
        "name_and_nickname": {},
        "profession": None,
        "preferences": {},
        "current_activities": [],
        "other_facts": {},
    }
    current: str | None = None
    for line in text[end + 6 :].splitlines():
        heading = line.strip()
        if heading == "## Name and nickname":
            current = "name_and_nickname"
        elif heading == "## Profession":
            current = "profession"
        elif heading == "## Preferences":
            current = "preferences"
        elif heading == "## Current activities":
            current = "current_activities"
        elif heading == "## Other durable facts":
            current = "other_facts"
        elif current and heading.startswith("- "):
            item = heading[2:].strip()
            if current == "current_activities":
                try:
                    parsed = json.loads(item)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, Mapping):
                    sections[current].append(dict(parsed))
            elif ":" in item:
                field, raw_entry = item.split(":", 1)
                try:
                    parsed = json.loads(raw_entry.strip())
                except json.JSONDecodeError:
                    continue
                if not isinstance(parsed, Mapping):
                    continue
                if current == "profession":
                    sections[current] = dict(parsed)
                else:
                    sections[current][field.strip()] = dict(parsed)
    metadata["sections"] = sections
    return metadata


def _render_markdown(payload: Mapping[str, Any]) -> str:
    sections = payload.get("sections") if isinstance(payload.get("sections"), Mapping) else {}
    lines = [
        "---",
        f"schema_version: {json.dumps(MEMORY_SCHEMA_VERSION)}",
        f"user_id: {json.dumps(str(payload.get('user_id', '')))}",
        f"created_at: {json.dumps(str(payload.get('created_at', _now())))}",
        f"updated_at: {json.dumps(str(payload.get('updated_at', _now())))}",
        "---",
        "# NexusOne personal memory",
        "",
        "<!-- Server-owned profile. Values are bounded non-sensitive user facts only. -->",
        "",
        "## Name and nickname",
    ]
    for field, entry in (sections.get("name_and_nickname") or {}).items():
        lines.append(f"- {field}: {json.dumps(entry, ensure_ascii=False, sort_keys=True)}")
    lines.extend(["", "## Profession"])
    profession = sections.get("profession")
    if isinstance(profession, Mapping):
        lines.append(f"- profession: {json.dumps(dict(profession), ensure_ascii=False, sort_keys=True)}")
    lines.extend(["", "## Preferences"])
    for field, entry in (sections.get("preferences") or {}).items():
        lines.append(f"- {field}: {json.dumps(entry, ensure_ascii=False, sort_keys=True)}")
    lines.extend(["", "## Current activities"])
    for entry in sections.get("current_activities") or []:
        lines.append(f"- {json.dumps(entry, ensure_ascii=False, sort_keys=True)}")
    lines.extend(["", "## Other durable facts"])
    for field, entry in (sections.get("other_facts") or {}).items():
        lines.append(f"- {field}: {json.dumps(entry, ensure_ascii=False, sort_keys=True)}")
    return "\n".join(lines) + "\n"


def _sanitized_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    sections = payload.get("sections") if isinstance(payload.get("sections"), Mapping) else {}
    names = _plain_mapping(sections.get("name_and_nickname"))
    profession_entry = sections.get("profession")
    profession = profession_entry.get("value") if isinstance(profession_entry, Mapping) else None
    preferences = _plain_mapping(sections.get("preferences"))
    activities = [
        item["value"]
        for item in sections.get("current_activities", [])
        if isinstance(item, Mapping) and isinstance(item.get("value"), str)
    ]
    other = _plain_mapping(sections.get("other_facts"))
    result: dict[str, Any] = {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "name_and_nickname": names,
        "profession": profession,
        "preferences": preferences,
        "current_activities": activities,
        "other_facts": other,
        # Compatibility aliases for the previous profile shape. These are
        # sanitized values only and contain no provenance or timestamps.
        "facts": {
            **({"name": names["name"]} if "name" in names else {}),
            **({"preferred_name": names["nickname"]} if "nickname" in names else {}),
            **({"profession": profession} if isinstance(profession, str) else {}),
            **other,
        },
    }
    return result


def _plain_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(field): str(entry["value"])
        for field, entry in value.items()
        if isinstance(field, str) and isinstance(entry, Mapping) and isinstance(entry.get("value"), str)
    }


def _merge_entries(target: dict[str, Any], values: Mapping[str, str], source: str, timestamp: str) -> None:
    for field, value in values.items():
        target[field] = _entry(value, source, timestamp)


def _entry(value: str, source: str, timestamp: str) -> dict[str, str]:
    return {"value": value, "source": source, "updated_at": timestamp}


def _entry_count(sections: Mapping[str, Any]) -> int:
    count = 0
    for group in ("name_and_nickname", "preferences", "other_facts"):
        value = sections.get(group)
        if isinstance(value, Mapping):
            count += len(value)
    if isinstance(sections.get("profession"), Mapping):
        count += 1
    activities = sections.get("current_activities")
    if isinstance(activities, Sequence) and not isinstance(activities, (str, bytes, bytearray)):
        count += len(activities)
    return count


def _trim_sections(sections: dict[str, Any]) -> None:
    remaining = MAX_MEMORY_FIELDS
    for group in ("name_and_nickname", "profession", "preferences", "current_activities", "other_facts"):
        value = sections.get(group)
        if group == "profession":
            if isinstance(value, Mapping) and remaining:
                remaining -= 1
            elif isinstance(value, Mapping):
                sections[group] = None
        elif isinstance(value, Mapping):
            kept = dict(list(value.items())[:remaining])
            sections[group] = kept
            remaining -= len(kept)
        elif isinstance(value, list):
            sections[group] = value[:remaining]
            remaining -= len(sections[group])


def _field_names(payload: Mapping[str, Any]) -> list[str]:
    sections = payload.get("sections") if isinstance(payload.get("sections"), Mapping) else {}
    fields: list[str] = []
    for group in ("name_and_nickname", "preferences", "other_facts"):
        value = sections.get(group)
        if isinstance(value, Mapping):
            fields.extend(str(field) for field in value if isinstance(field, str))
    if isinstance(sections.get("profession"), Mapping):
        fields.append("profession")
    if sections.get("current_activities"):
        fields.append("current_activities")
    return fields[:MAX_MEMORY_FIELDS]


def _input_field_names(*groups: Mapping[str, Any] | None) -> tuple[str, ...]:
    fields: list[str] = []
    for group in groups:
        if isinstance(group, Mapping):
            fields.extend(str(field)[:48] for field in group if isinstance(field, str))
    return tuple(fields[:MAX_MEMORY_FIELDS])


def _safe_source(value: Any) -> str:
    if not isinstance(value, str):
        return "explicit_user"
    clean = re.sub(r"[^a-zA-Z0-9_.:-]", "_", value.strip())[:48]
    return clean or "explicit_user"


def _safe_timestamp(value: Any) -> str:
    if isinstance(value, str) and value and len(value) <= 64:
        return value
    return _now()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _lock_for(path: Path) -> threading.RLock:
    key = path.resolve()
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


class _file_lock:
    """Best-effort advisory lock for local multi-process workers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        if self.handle is None:
            return
        try:
            import fcntl

            fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        self.handle.close()


JSONUserMemoryStore = MarkdownUserMemoryStore

__all__ = [
    "JSONUserMemoryStore",
    "MarkdownUserMemoryStore",
    "MAX_ACTIVITY_ITEMS",
    "MAX_MEMORY_FIELDS",
    "MEMORY_SCHEMA_VERSION",
    "MemoryValidationError",
    "UserMemoryStore",
]
