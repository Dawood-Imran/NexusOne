"""Server-controlled long-term memory tools.

The LangChain tool schemas deliberately contain no ``user_id``, path, role, or
permission fields. A tool instance closes over an immutable runtime context
created by the authenticated server, so a model can request a read/update but
cannot select the profile namespace or alter access policy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.auth.profiles import get_profile
from app.memory.user_memory import JSONUserMemoryStore, UserMemoryStore


@dataclass(frozen=True)
class MemoryRuntimeContext:
    """Identity and policy flags injected by the authenticated server.

    Callers should use :meth:`from_session` in the HTTP path. The user ID is
    retained only inside this server-owned closure and is never a model tool
    argument.
    """

    authenticated_user_id: str
    preference_opt_in: bool = False
    explicit_user_input: bool = False
    runtime_source: str = "authenticated_session"

    @classmethod
    def from_session(cls, session: Any, *, explicit_user_input: bool = False, preference_opt_in: bool = False) -> "MemoryRuntimeContext":
        user_id = getattr(session, "user_id", None)
        if not isinstance(user_id, str) or not user_id:
            raise PermissionError("authenticated session identity is required")
        return cls(
            authenticated_user_id=user_id,
            preference_opt_in=preference_opt_in,
            explicit_user_input=explicit_user_input,
        )


class UserMemoryTools:
    """Python implementation behind both model tools."""

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
        identity_fields = {"user_id", "authenticated_user_id", "owner_user_id", "path", "file_path"}
        if any(key in updates for key in identity_fields):
            raise PermissionError("memory identity is server controlled")
        allowed = {
            "name_and_nickname",
            "profession",
            "preferences",
            "current_activities",
            "other_facts",
            # Compatibility only; the public model schema does not advertise
            # this older shape.
            "facts",
        }
        if any(key not in allowed for key in updates):
            raise PermissionError("memory tools cannot change policy or access settings")
        values = {key: updates.get(key) for key in allowed if key in updates}
        if values.get("profession") is not None and not isinstance(values["profession"], str):
            raise ValueError("profession must be text")
        for key in ("name_and_nickname", "preferences", "other_facts", "facts"):
            if values.get(key) is not None and not isinstance(values[key], Mapping):
                raise ValueError(f"{key} must be an object")
        activities = values.get("current_activities")
        if activities is not None and not isinstance(activities, (list, tuple, str)):
            raise ValueError("current_activities must be a list of text")
        return self.store.update(
            runtime.authenticated_user_id,
            name_and_nickname=values.get("name_and_nickname"),
            profession=values.get("profession"),
            preferences=values.get("preferences"),
            current_activities=activities,
            other_facts=values.get("other_facts"),
            facts=values.get("facts"),
            source="explicit_user",
            preference_opt_in=runtime.preference_opt_in,
        )


def get_user_memory(
    runtime: MemoryRuntimeContext,
    *,
    store: UserMemoryStore | None = None,
) -> dict[str, Any]:
    """Read only the authenticated user's sanitized profile."""

    return UserMemoryTools(store or _default_store()).get_user_memory(runtime)


def update_user_memory(
    runtime: MemoryRuntimeContext,
    updates: Mapping[str, Any],
    *,
    store: UserMemoryStore | None = None,
) -> dict[str, Any]:
    """Update explicit, validated facts/preferences in the injected namespace."""

    return UserMemoryTools(store or _default_store()).update_user_memory(runtime, updates)


def build_langchain_memory_tools(
    runtime: MemoryRuntimeContext,
    *,
    store: UserMemoryStore,
) -> list[Any]:
    """Build the two explicit LangChain tools for one authenticated turn.

    The import is lazy so the file-backed store remains usable by isolated
    storage tests even when the optional LangChain provider packages are not
    installed. Tool construction fails closed rather than silently exposing a
    weaker, model-controlled identity path.
    """

    try:
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel, ConfigDict, Field
    except ImportError as exc:  # pragma: no cover - dependency installation boundary.
        raise RuntimeError("LangChain core is required to build memory tools") from exc

    class GetUserMemoryInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

    class NameAndNicknameInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        name: str | None = Field(default=None, max_length=80)
        nickname: str | None = Field(default=None, max_length=80)

    class PreferencesInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        language: str | None = Field(default=None, max_length=120)
        response_style: str | None = Field(default=None, max_length=120)
        date_format: str | None = Field(default=None, max_length=120)
        communication_channel: str | None = Field(default=None, max_length=120)
        theme: str | None = Field(default=None, max_length=120)
        notification_style: str | None = Field(default=None, max_length=120)
        food_preference: str | None = Field(default=None, max_length=120)
        drink_preference: str | None = Field(default=None, max_length=120)

    class OtherFactsInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        working_timezone: str | None = Field(default=None, max_length=120)
        office_location: str | None = Field(default=None, max_length=120)
        team: str | None = Field(default=None, max_length=120)
        hobby: str | None = Field(default=None, max_length=120)
        pronouns: str | None = Field(default=None, max_length=120)
        favorite_color: str | None = Field(default=None, max_length=120)
        favorite_food: str | None = Field(default=None, max_length=120)

    class UpdateUserMemoryInput(BaseModel):
        model_config = ConfigDict(extra="forbid")

        name_and_nickname: NameAndNicknameInput | None = Field(default=None)
        profession: str | None = Field(default=None, max_length=120)
        preferences: PreferencesInput | None = Field(default=None)
        current_activities: list[str] | None = Field(default=None, max_length=5)
        other_facts: OtherFactsInput | None = Field(default=None)

    manager = UserMemoryTools(store)

    def _get_user_memory() -> dict[str, Any]:
        return manager.get_user_memory(runtime)

    def _update_user_memory(**kwargs: Any) -> dict[str, Any]:
        normalized = {
            key: value.model_dump(exclude_none=True) if isinstance(value, BaseModel) else value
            for key, value in kwargs.items()
        }
        return manager.update_user_memory(runtime, normalized)

    return [
        StructuredTool.from_function(
            name="get_user_memory",
            description=(
                "Retrieve the authenticated user's sanitized durable personal profile. "
                "Use for personal facts or preferences only. Identity is supplied by the server; "
                "never ask for or provide a user ID or file path."
            ),
            func=_get_user_memory,
            args_schema=GetUserMemoryInput,
            infer_schema=False,
        ),
        StructuredTool.from_function(
            name="update_user_memory",
            description=(
                "Store an explicit, user-provided non-sensitive durable fact or preference in the "
                "authenticated user's profile. Use only when the current user clearly states a fact "
                "or preference they want remembered. Never store assistant text, retrieved documents, "
                "secrets, credentials, permissions, roles, or identity/path selectors."
            ),
            func=_update_user_memory,
            args_schema=UpdateUserMemoryInput,
            infer_schema=False,
        ),
    ]


def memory_tool_contract() -> dict[str, dict[str, Any]]:
    """Return provider-independent schemas for audit/tests/documentation."""

    return {
        "get_user_memory": {
            "description": "Retrieve the authenticated user's sanitized durable personal profile.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
        "update_user_memory": {
            "description": "Store an explicit, user-provided non-sensitive durable fact or preference.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name_and_nickname": {
                        "type": "object",
                        "properties": {"name": {"type": "string", "maxLength": 80}, "nickname": {"type": "string", "maxLength": 80}},
                        "additionalProperties": False,
                    },
                    "profession": {"type": "string", "maxLength": 120},
                    "preferences": {
                        "type": "object",
                        "properties": {
                            key: {"type": "string", "maxLength": 120}
                            for key in ("language", "response_style", "date_format", "communication_channel", "theme", "notification_style", "food_preference", "drink_preference")
                        },
                        "additionalProperties": False,
                    },
                    "current_activities": {"type": "array", "items": {"type": "string", "maxLength": 120}, "maxItems": 5},
                    "other_facts": {
                        "type": "object",
                        "properties": {
                            key: {"type": "string", "maxLength": 120}
                            for key in ("working_timezone", "office_location", "team", "hobby", "pronouns", "favorite_color", "favorite_food")
                        },
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
        },
    }


def _require_runtime(runtime: MemoryRuntimeContext) -> None:
    if (
        not isinstance(runtime, MemoryRuntimeContext)
        or not runtime.authenticated_user_id
        or get_profile(runtime.authenticated_user_id) is None
        or get_profile(runtime.authenticated_user_id).status != "active"
    ):
        raise PermissionError("authenticated runtime context is required")


def _default_store() -> JSONUserMemoryStore:
    from app.runtime.config import RuntimeConfig

    config = RuntimeConfig.from_env()
    return JSONUserMemoryStore(config.user_memory_dir)


__all__ = [
    "MemoryRuntimeContext",
    "UserMemoryTools",
    "build_langchain_memory_tools",
    "get_user_memory",
    "memory_tool_contract",
    "update_user_memory",
]
