"""Result packaging for SQL subgraph outputs."""

from __future__ import annotations

import hashlib
from typing import Mapping

from app.agents.sql_subgraph.state import (
    SQLExecutionResult,
    SQLSubgraphOutput,
    SourceDefinition,
)


def query_id_for(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()[:16]


def source_metadata(sources: tuple[SourceDefinition, ...], used_sources: tuple[str, ...]) -> tuple[Mapping[str, str], ...]:
    used = set(used_sources)
    return tuple(
        {
            "name": source.name,
            "kind": source.kind,
            "domain": source.domain,
            "description": source.description,
        }
        for source in sources
        if source.name in used
    )


def format_validated_output(
    sql: str,
    parameters: Mapping[str, object],
    sources: tuple[SourceDefinition, ...],
    used_sources: tuple[str, ...],
) -> SQLSubgraphOutput:
    return SQLSubgraphOutput(
        sql_status="validated",
        sql_answer_summary="Validated SQL is ready to execute; no database executor was provided or execution was disabled.",
        sql_sources=source_metadata(sources, used_sources),
        sql_used_tables=used_sources,
        sql_query=sql,
        sql_query_id=query_id_for(sql),
        sql_parameters=dict(parameters),
    )


def format_execution_output(
    sql: str,
    parameters: Mapping[str, object],
    sources: tuple[SourceDefinition, ...],
    used_sources: tuple[str, ...],
    execution_result: SQLExecutionResult,
) -> SQLSubgraphOutput:
    summary = f"Structured query returned {execution_result.row_count} row(s)."
    return SQLSubgraphOutput(
        sql_status="answered",
        sql_answer_summary=summary,
        sql_rows=execution_result.rows,
        sql_columns=execution_result.columns,
        sql_sources=source_metadata(sources, used_sources),
        sql_used_tables=used_sources,
        sql_query=sql,
        sql_query_id=query_id_for(sql),
        sql_parameters=dict(parameters),
    )


def format_refusal(reason: str, status: str = "refused") -> SQLSubgraphOutput:
    return SQLSubgraphOutput(
        sql_status=status,  # type: ignore[arg-type]
        sql_answer_summary=reason,
        sql_denied_reason=reason,
    )


def format_error(message: str) -> SQLSubgraphOutput:
    return SQLSubgraphOutput(
        sql_status="error",
        sql_answer_summary="The SQL subgraph could not complete the structured-data request.",
        sql_error=message,
    )

