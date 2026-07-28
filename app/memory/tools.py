"""Server-controlled long-term memory tools.

The callable surface intentionally takes an authenticated runtime context rather
than a user ID argument. A model can request these tools, but it cannot select
the namespace, alter permissions, widen retrieval scope, or provide another
identity. Preference writes require an explicit opt-in in the server context.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.memory.user_memory import JSONUserMemoryStore, UserMemoryStore


@dataclass(frozen=True)
class MemoryRuntimeContext:
    """Immutable identity/context injected by the authenticated server."""

    authenticated_user_id: str
    preference_opt_in: bool = False
    explicit_user_input: bool = False


class UserMemoryTools:
    """Equivalent to ``get_user_memory``/``update_user_memory`` tool calls."""

    def __init__(self, store: UserMemoryStore) -> None:
        self.store = store

    def get_user_memory(self, runtime: MemoryRuntimeContext) -> dict[str, Any]:
        _require_runtime(runtime)
        return self.store.read(runtime.authenticated_user_id)

    def update_user_memory(
        self,
        runtime: MemoryRuntimeContext,
        updates: Mapping[str, Any],
    ) -> dict[str, Any]:
        _require_runtime(runtime)
        if not runtime.explicit_user_input:
            raise PermissionError("memory updates require explicit user input")
        if not isinstance(updates, Mapping):
            raise ValueError("updates must be an object")
        # A tool schema should never expose this field, and rejecting it here
        # keeps a malformed/model-supplied payload from becoming an identity
        # boundary even if a future adapter passes arbitrary JSON through.
        if any(key in updates for key in ("user_id", "authenticated_user_id", "owner_user_id")):
            raise PermissionError("memory identity is server controlled")
        if any(key not in {"facts", "preferences"} for key in updates):
            raise PermissionError("memory tools cannot change policy or access settings")
        facts = updates.get("facts")
        preferences = updates.get("preferences")
        if facts is not None and not isinstance(facts, Mapping):
            raise ValueError("facts must be an object")
        if preferences is not None and not isinstance(preferences, Mapping):
            raise ValueError("preferences must be an object")
        return self.store.update(
            runtime.authenticated_user_id,
            facts=facts,
            preferences=preferences,
            source="explicit_user",
            preference_opt_in=runtime.preference_opt_in,
        )


def get_user_memory(
    runtime: MemoryRuntimeContext,
    *,
    store: UserMemoryStore | None = None,
) -> dict[str, Any]:
    """Read only the authenticated user's sanitized profile memory."""

    return UserMemoryTools(store or _default_store()).get_user_memory(runtime)


def update_user_memory(
    runtime: MemoryRuntimeContext,
    updates: Mapping[str, Any],
    *,
    store: UserMemoryStore | None = None,
) -> dict[str, Any]:
    """Update explicit, validated facts/preferences in the injected namespace."""

    return UserMemoryTools(store or _default_store()).update_user_memory(runtime, updates)


def _require_runtime(runtime: MemoryRuntimeContext) -> None:
    if not isinstance(runtime, MemoryRuntimeContext) or not runtime.authenticated_user_id:
        raise PermissionError("authenticated runtime context is required")


def _default_store() -> JSONUserMemoryStore:
    from app.runtime.config import RuntimeConfig

    config = RuntimeConfig.from_env()
    return JSONUserMemoryStore(config.user_memory_dir)


__all__ = [
    "MemoryRuntimeContext",
    "UserMemoryTools",
    "get_user_memory",
    "update_user_memory",
]
