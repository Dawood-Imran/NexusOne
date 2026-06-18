"""Permission and scope selection for the SQL subgraph."""

from __future__ import annotations

from app.agents.sql_subgraph.schema_registry import sources_for_intent
from app.agents.sql_subgraph.state import SourceDefinition, UserContext


def is_active_user(user_context: UserContext | None) -> bool:
    return user_context is not None and user_context.status == "active"


def source_allowed_for_user(source: SourceDefinition, user_context: UserContext) -> bool:
    if not is_active_user(user_context):
        return False
    if source.access_roles == "all_active":
        return True
    return user_context.role in source.access_roles


def select_allowed_sources(user_context: UserContext, intent: str) -> tuple[SourceDefinition, ...]:
    candidates = sources_for_intent(intent)
    return tuple(source for source in candidates if source_allowed_for_user(source, user_context))


def describe_denial(user_context: UserContext | None, intent: str) -> str:
    if user_context is None:
        return "User context is missing."
    if user_context.status != "active":
        return "The user is not active."
    return f"Role '{user_context.role}' is not allowed to query structured source intent '{intent}'."

