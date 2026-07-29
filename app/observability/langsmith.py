"""LangSmith-compatible runtime config for graph invocations."""

from __future__ import annotations

from typing import Any, Mapping


RUN_NAME = "nexusone_main_orchestrator"
SAFE_ROUTE_NAMES = frozenset(
    {
        "rag",
        "ticket_guidance",
        "sql",
        "combined",
        "ticket_create",
        "CASUAL",
        "GENERAL_KNOWLEDGE",
        "feedback",
        "clarification",
        "unsupported",
        "deny",
        "error",
    }
)


def build_langsmith_config(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build safe LangGraph/LangSmith config.

    This intentionally excludes user message text, retrieved chunks, SQL text,
    final answers, and source excerpts. Those can be sensitive or too verbose.
    """

    user_id = str(payload.get("user_id", "unknown"))
    execute_sql = bool(payload.get("execute_sql", False))
    include_trace = bool(payload.get("include_trace", False))
    metadata = {
        "app": "nexusone_copilot",
        "phase": "phase_3_orchestrator",
        "conversation_id": str(payload.get("conversation_id", "web-chat")),
        "turn_id": str(payload.get("turn_id", "web-turn")),
        "user_id": user_id,
        "execute_sql": execute_sql,
        "ui_trace_requested": include_trace,
    }
    route = payload.get("route")
    if not isinstance(route, str) or route not in SAFE_ROUTE_NAMES:
        route = None
    if route:
        metadata["route"] = route
    tags = [
        "nexusone",
        "orchestrator",
        "phase-3",
        f"user:{user_id}",
        "sql-execute" if execute_sql else "sql-validate-only",
    ]
    if route:
        tags.append(f"route:{route}")
    # LangGraph checkpointers use this same value as their thread key. The
    # current graph also has the repository-owned SQLite turn store, so this
    # remains useful when a production checkpointer is introduced.
    return {
        "run_name": RUN_NAME,
        "tags": tags,
        "metadata": metadata,
        "configurable": {
            "thread_id": str(payload.get("conversation_id", "web-chat")),
        },
    }
