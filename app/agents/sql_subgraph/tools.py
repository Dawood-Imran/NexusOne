"""Internal tools for the SQL subgraph."""

from __future__ import annotations

from typing import Mapping

from app.agents.sql_subgraph.permissions import select_allowed_sources
from app.agents.sql_subgraph.state import SQLExecutor, SQLExecutionResult, SourceDefinition, UserContext


def sql_list_allowed_sources(user_context: UserContext, intent: str) -> tuple[SourceDefinition, ...]:
    return select_allowed_sources(user_context, intent)


def sql_get_schema_context(sources: tuple[SourceDefinition, ...]) -> str:
    sections: list[str] = []
    for source in sources:
        columns = "\n".join(f"- {column.name}: {column.description}" for column in source.columns)
        sections.append(
            "\n".join(
                [
                    f"Source: {source.name}",
                    f"Kind: {source.kind}",
                    f"Domain: {source.domain}",
                    f"Description: {source.description}",
                    "Columns:",
                    columns,
                    f"Max rows: {source.max_rows}",
                    f"Requires user_id: {source.requires_user_id}",
                ]
            )
        )
    return "\n\n".join(sections)


def sql_execute_readonly(
    executor: SQLExecutor,
    query: str,
    parameters: Mapping[str, object],
    max_rows: int,
) -> SQLExecutionResult:
    return executor.fetch_all(query, parameters, max_rows)
