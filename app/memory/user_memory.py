"""Validated, server-owned long-term user memory stored as local JSON files."""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.auth.profiles import get_profile


MEMORY_SCHEMA_VERSION = 1
MAX_MEMORY_FIELDS = 8
MAX_VALUE_CHARS = 120
MAX_PREFERRED_NAME_CHARS = 80
_SAFE_USER_ID = re.compile(r"^u[0-9]{3}$")
_SENSITIVE_FIELD = re.compile(
    r"(password|passwd|secret|token|api[_ -]?key|credential|ssn|social|salary|bank|card|medical|health|diagnos)",
    re.IGNORECASE,
)
_ALLOWED_FACT_FIELDS = frozenset({"preferred_name", "working_timezone", "office_location"})
_ALLOWED_PREFERENCE_FIELDS = frozenset({"language", "response_style", "date_format", "communication_channel"})
_ALLOWED_RESPONSE_STYLES = frozenset({"concise", "balanced", "detailed"})
_ALLOWED_DATE_FORMATS = frozenset({"iso", "day_first", "month_first"})
_ALLOWED_CHANNELS = frozenset({"email", "chat", "slack"})


class MemoryValidationError(ValueError):
    """A user memory update failed the bounded safe schema."""


class UserMemoryStore(Protocol):
    def read(self, user_id: str) -> dict[str, Any]: ...

    def update(
        self,
        user_id: str,
        *,
        facts: Mapping[str, Any] | None = None,
        preferences: Mapping[str, Any] | None = None,
        source: str = "explicit_user",
        preference_opt_in: bool = False,
    ) -> dict[str, Any]: ...


# Locks are process-wide so two store instances in the local server still
# serialize updates to the same profile file. Atomic replace protects readers
# and fcntl locking below protects separate local worker processes when present.
_LOCKS: dict[Path, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


class JSONUserMemoryStore:
    """File-backed per-user memory with atomic writes and safe audit metadata.

    The only accepted path component is a known synthetic user ID (``u001`` …
    ``u008``). The store never joins an arbitrary caller-provided path.
    """

    def __init__(self, root_dir: str | Path, *, audit_path: str | Path | None = None) -> None:
        self.root_dir = Path(root_dir).expanduser().resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.audit_path = (Path(audit_path).expanduser().resolve() if audit_path else self.root_dir / "memory_audit.jsonl")
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
        facts: Mapping[str, Any] | None = None,
        preferences: Mapping[str, Any] | None = None,
        source: str = "explicit_user",
        preference_opt_in: bool = False,
    ) -> dict[str, Any]:
        safe_user_id = _validated_user_id(user_id)
        try:
            normalized_facts = _validate_fields(facts, _ALLOWED_FACT_FIELDS, "facts")
            normalized_preferences = _validate_fields(preferences, _ALLOWED_PREFERENCE_FIELDS, "preferences")
        except MemoryValidationError:
            self._audit(safe_user_id, "update_user_memory", "rejected", _input_field_names(facts, preferences))
            raise
        if normalized_preferences and not preference_opt_in:
            self._audit(safe_user_id, "update_user_memory", "preference_opt_in_required", tuple(normalized_preferences))
            raise MemoryValidationError("explicit preference opt-in is required")
        if not normalized_facts and not normalized_preferences:
            raise MemoryValidationError("at least one supported memory field is required")
        if len(normalized_facts) + len(normalized_preferences) > MAX_MEMORY_FIELDS:
            raise MemoryValidationError("too many memory fields")
        safe_source = _safe_source(source)
        path = self._profile_path(safe_user_id)
        lock = _lock_for(path)
        with lock, _file_lock(path.with_suffix(".lock")):
            payload = self._read_payload(path, safe_user_id)
            now = _now()
            facts_payload = payload.setdefault("facts", {})
            preferences_payload = payload.setdefault("preferences", {})
            for field, value in normalized_facts.items():
                facts_payload[field] = {"value": value, "source": safe_source, "updated_at": now}
            for field, value in normalized_preferences.items():
                preferences_payload[field] = {"value": value, "source": safe_source, "updated_at": now}
            payload["schema_version"] = MEMORY_SCHEMA_VERSION
            payload["user_id"] = safe_user_id
            self._atomic_write(path, payload)
        changed_fields = tuple([*normalized_facts.keys(), *normalized_preferences.keys()])
        self._audit(safe_user_id, "update_user_memory", "ok", changed_fields)
        return _sanitized_payload(payload)

    def profile_path(self, user_id: str) -> Path:
        """Expose the safe resolved path for tests/diagnostics, not arbitrary paths."""

        return self._profile_path(_validated_user_id(user_id))

    def _profile_path(self, user_id: str) -> Path:
        # user_id has already been validated against the server manifest.
        return self.root_dir / f"{user_id}.json"

    def _read_payload(self, path: Path, user_id: str) -> dict[str, Any]:
        if not path.exists():
            return {
                "schema_version": MEMORY_SCHEMA_VERSION,
                "user_id": user_id,
                "facts": {},
                "preferences": {},
            }
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, UnicodeError):
            self._audit(user_id, "get_user_memory", "invalid_file_reset", ())
            return {
                "schema_version": MEMORY_SCHEMA_VERSION,
                "user_id": user_id,
                "facts": {},
                "preferences": {},
            }
        if not isinstance(raw, Mapping) or raw.get("schema_version") != MEMORY_SCHEMA_VERSION:
            self._audit(user_id, "get_user_memory", "schema_reset", ())
            return {
                "schema_version": MEMORY_SCHEMA_VERSION,
                "user_id": user_id,
                "facts": {},
                "preferences": {},
            }
        return _normalize_existing_payload(raw, user_id)

    def _atomic_write(self, path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        try:
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _audit(self, user_id: str, action: str, outcome: str, fields: tuple[str, ...]) -> None:
        event = {
            "timestamp": _now(),
            "action": action,
            "user_id": user_id,
            "outcome": outcome,
            "fields": list(fields)[:MAX_MEMORY_FIELDS],
        }
        lock = _lock_for(self.audit_path)
        with lock:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, separators=(",", ":")) + "\n")


def _validated_user_id(value: Any) -> str:
    if not isinstance(value, str) or not _SAFE_USER_ID.fullmatch(value) or get_profile(value) is None:
        raise MemoryValidationError("memory identity must be an authenticated NexusOne user")
    return value


def _validate_fields(
    values: Mapping[str, Any] | None,
    allowed: frozenset[str],
    group: str,
) -> dict[str, str]:
    if values is None:
        return {}
    if not isinstance(values, Mapping):
        raise MemoryValidationError(f"{group} must be an object")
    normalized: dict[str, str] = {}
    for field, value in values.items():
        if not isinstance(field, str) or not field or _SENSITIVE_FIELD.search(field) or field not in allowed:
            raise MemoryValidationError("unsupported or sensitive memory field")
        if not isinstance(value, str):
            raise MemoryValidationError("memory values must be text")
        clean = _normalize_value(value, field)
        if not clean:
            raise MemoryValidationError("memory values must not be empty")
        normalized[field] = clean
    return normalized


def _normalize_value(value: str, field: str) -> str:
    clean = re.sub(r"\s+", " ", value.replace("\x00", " ")).strip()
    maximum = MAX_PREFERRED_NAME_CHARS if field == "preferred_name" else MAX_VALUE_CHARS
    if len(clean) > maximum or "\n" in value or "\r" in value:
        raise MemoryValidationError("memory value is too long or contains a line break")
    lowered = clean.casefold()
    if _SENSITIVE_FIELD.search(field) or any(
        marker in lowered
        for marker in (
            "sk-",
            "bearer ",
            "password=",
            "token=",
            "ignore previous",
            "system prompt",
            "reveal hidden",
            "follow these instructions",
        )
    ):
        raise MemoryValidationError("sensitive or instruction-like values are not stored")
    if field == "response_style" and lowered not in _ALLOWED_RESPONSE_STYLES:
        raise MemoryValidationError("unsupported response style")
    if field == "date_format" and lowered not in _ALLOWED_DATE_FORMATS:
        raise MemoryValidationError("unsupported date format")
    if field == "communication_channel" and lowered not in _ALLOWED_CHANNELS:
        raise MemoryValidationError("unsupported communication channel")
    if field == "language" and not re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]{0,39}", clean):
        raise MemoryValidationError("unsupported language value")
    return clean


def _normalize_existing_payload(raw: Mapping[str, Any], user_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": MEMORY_SCHEMA_VERSION,
        "user_id": user_id,
        "facts": {},
        "preferences": {},
    }
    for group, allowed in (("facts", _ALLOWED_FACT_FIELDS), ("preferences", _ALLOWED_PREFERENCE_FIELDS)):
        source_group = raw.get(group)
        if not isinstance(source_group, Mapping):
            continue
        for field, entry in source_group.items():
            if field not in allowed or not isinstance(entry, Mapping):
                continue
            value = entry.get("value")
            source = entry.get("source")
            updated_at = entry.get("updated_at")
            if not isinstance(value, str) or not isinstance(source, str) or not isinstance(updated_at, str):
                continue
            try:
                clean = _normalize_value(value, field)
            except MemoryValidationError:
                continue
            result[group][field] = {
                "value": clean,
                "source": _safe_source(source),
                "updated_at": updated_at[:64],
            }
    return result


def _sanitized_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"schema_version": MEMORY_SCHEMA_VERSION, "facts": {}, "preferences": {}}
    for group in ("facts", "preferences"):
        source_group = payload.get(group)
        if not isinstance(source_group, Mapping):
            continue
        for field, entry in source_group.items():
            if isinstance(field, str) and isinstance(entry, Mapping) and isinstance(entry.get("value"), str):
                result[group][field] = entry["value"]
    return result


def _input_field_names(*groups: Mapping[str, Any] | None) -> tuple[str, ...]:
    fields: list[str] = []
    for group in groups:
        if isinstance(group, Mapping):
            fields.extend(str(field)[:48] for field in group if isinstance(field, str))
    return tuple(fields[:MAX_MEMORY_FIELDS])


def _field_names(payload: Mapping[str, Any]) -> list[str]:
    fields: list[str] = []
    for group in ("facts", "preferences"):
        source_group = payload.get(group)
        if isinstance(source_group, Mapping):
            fields.extend(str(field) for field in source_group if isinstance(field, str))
    return fields[:MAX_MEMORY_FIELDS]


def _safe_source(value: Any) -> str:
    if not isinstance(value, str):
        return "explicit_user"
    clean = re.sub(r"[^a-zA-Z0-9_.:-]", "_", value.strip())[:48]
    return clean or "explicit_user"


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


__all__ = [
    "JSONUserMemoryStore",
    "MAX_MEMORY_FIELDS",
    "MEMORY_SCHEMA_VERSION",
    "MemoryValidationError",
    "UserMemoryStore",
]
