"""Deterministic SQL safety validator for the SQL subgraph.

This validator is intentionally conservative. It is not a full SQL parser, but it
enforces the core safety properties before any model-generated SQL can execute.
When sqlglot is added later, this module can keep the same public interface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.sql_subgraph.state import SQLValidationResult, SourceDefinition


BLOCKED_KEYWORDS = {
    "alter",
    "call",
    "copy",
    "create",
    "delete",
    "do",
    "drop",
    "execute",
    "grant",
    "insert",
    "merge",
    "revoke",
    "truncate",
    "update",
}

SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}


@dataclass(frozen=True)
class ValidatorConfig:
    default_max_rows: int = 25


def normalize_sql(sql: str) -> str:
    normalized = " ".join(sql.strip().split())
    if normalized.endswith(";"):
        normalized = normalized[:-1].strip()
    return normalized


def contains_comments(sql: str) -> bool:
    return "--" in sql or "/*" in sql or "*/" in sql


def has_multiple_statements(sql: str) -> bool:
    stripped = sql.strip()
    if not stripped:
        return False
    if stripped.endswith(";"):
        stripped = stripped[:-1]
    return ";" in stripped


def starts_readonly(sql: str) -> bool:
    lowered = sql.lstrip().lower()
    return lowered.startswith("select ") or lowered.startswith("with ")


def blocked_keyword(sql: str) -> str | None:
    lowered = sql.lower()
    for keyword in sorted(BLOCKED_KEYWORDS):
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            return keyword
    return None


def clean_source_name(raw_name: str) -> str:
    name = raw_name.strip().strip('"')
    if "." in name:
        schema, table = name.split(".", 1)
        if schema.strip('"').lower() in SYSTEM_SCHEMAS:
            return f"{schema.strip().lower()}.{table.strip().lower()}"
        name = table
    return name.strip('"').lower()


def extract_source_names(sql: str) -> tuple[str, ...]:
    pattern = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][\w.\"\$]*)", re.IGNORECASE)
    names: list[str] = []
    for match in pattern.finditer(sql):
        raw_name = match.group(1)
        if raw_name.startswith("("):
            continue
        cleaned = clean_source_name(raw_name)
        if cleaned not in names:
            names.append(cleaned)
    return tuple(names)


def extract_limit(sql: str) -> int | None:
    matches = re.findall(r"\blimit\s+(\d+)\b", sql, flags=re.IGNORECASE)
    if not matches:
        return None
    return int(matches[-1])


def appears_single_aggregate(sql: str) -> bool:
    lowered = sql.lower()
    aggregate = re.search(r"\b(count|sum|avg|min|max)\s*\(", lowered) is not None
    grouped = re.search(r"\bgroup\s+by\b", lowered) is not None
    return aggregate and not grouped


def enforce_limit(sql: str, max_rows: int) -> str:
    current_limit = extract_limit(sql)
    if current_limit is None:
        return f"SELECT * FROM ({sql}) AS limited_query LIMIT {max_rows}"
    if current_limit > max_rows:
        return re.sub(r"\blimit\s+\d+\b", f"LIMIT {max_rows}", sql, flags=re.IGNORECASE)
    return sql


def requires_user_id_check(source: SourceDefinition, sql: str) -> bool:
    if not source.requires_user_id:
        return True
    lowered = sql.lower()
    if source.kind == "function":
        return f"{source.name.lower()}(:user_id" in lowered
    return re.search(r"\buser_id\s*=\s*:user_id\b", lowered) is not None


def validate_sql(
    sql: str,
    allowed_sources: tuple[SourceDefinition, ...],
    config: ValidatorConfig | None = None,
) -> SQLValidationResult:
    config = config or ValidatorConfig()

    if not sql or not sql.strip():
        return SQLValidationResult(False, reason="SQL is empty.")
    if contains_comments(sql):
        return SQLValidationResult(False, reason="SQL comments are not allowed.")
    if has_multiple_statements(sql):
        return SQLValidationResult(False, reason="Multiple SQL statements are not allowed.")

    normalized = normalize_sql(sql)
    if not starts_readonly(normalized):
        return SQLValidationResult(False, reason="Only SELECT or read-only WITH queries are allowed.")

    keyword = blocked_keyword(normalized)
    if keyword is not None:
        return SQLValidationResult(False, reason=f"Blocked SQL keyword: {keyword}.")

    used_sources = extract_source_names(normalized)
    if not used_sources:
        return SQLValidationResult(False, reason="Query does not reference an allowed source.")

    for source in used_sources:
        if "." in source and source.split(".", 1)[0] in SYSTEM_SCHEMAS:
            return SQLValidationResult(False, reason=f"System schema access is not allowed: {source}.")

    allowed_by_name = {source.name.lower(): source for source in allowed_sources}
    unknown_sources = tuple(source for source in used_sources if source not in allowed_by_name)
    if unknown_sources:
        return SQLValidationResult(
            False,
            reason=f"Query references non-allowlisted source(s): {', '.join(unknown_sources)}.",
            used_sources=used_sources,
        )

    for source_name in used_sources:
        source = allowed_by_name[source_name]
        if not requires_user_id_check(source, normalized):
            return SQLValidationResult(
                False,
                reason=f"Source '{source.name}' requires a :user_id filter or function argument.",
                used_sources=used_sources,
            )

    max_rows = min((source.max_rows for source in allowed_sources), default=config.default_max_rows)
    rewritten = None
    if not appears_single_aggregate(normalized):
        limited = enforce_limit(normalized, max_rows)
        if limited != normalized:
            rewritten = limited

    return SQLValidationResult(
        True,
        used_sources=used_sources,
        normalized_sql=normalized,
        rewritten_sql=rewritten,
    )

