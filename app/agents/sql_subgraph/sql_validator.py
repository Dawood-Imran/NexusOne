"""Deterministic SQL safety validator for the SQL subgraph."""

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

HIDDEN_OUTPUT_COLUMNS = {
    "requester_id",
    "assigned_to",
    "actor_user_id",
    "manager_id",
    "admin_contact",
    "escalation_contact",
    "owner",
    "user_id",
    "confidentiality",
    "source_path",
    "docs_path",
}


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


def _select_projection(sql: str) -> str:
    match = re.search(r"^\s*select\s+(.*?)\s+from\s+", sql, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return match.group(1)


def _projected_identifiers(sql: str) -> set[str]:
    projection = _select_projection(sql)
    if not projection:
        return set()
    identifiers: set[str] = set()
    for part in projection.split(","):
        token = part.strip()
        if not token:
            continue
        if token == "*":
            identifiers.add("*")
            continue
        if token.endswith(".*"):
            identifiers.add("*")
            continue
        alias_match = re.search(r"\bas\s+([a-zA-Z_][\w]*)$", token, flags=re.IGNORECASE)
        if alias_match:
            identifiers.add(alias_match.group(1).lower())
        first = token.split()[0].split(".")[-1].strip('"').lower()
        if re.match(r"^[a-zA-Z_][\w]*$", first):
            identifiers.add(first)
    return identifiers


def validate_sql(
    sql: str,
    allowed_sources: tuple[SourceDefinition, ...],
    config: ValidatorConfig | None = None,
) -> SQLValidationResult:
    config = config or ValidatorConfig()

    if not sql or not sql.strip():
        return SQLValidationResult(False, reason="SQL is empty.", feedback_for_repair="Draft a single SELECT query.")
    if contains_comments(sql):
        return SQLValidationResult(False, reason="SQL comments are not allowed.", feedback_for_repair="Remove SQL comments.")
    if has_multiple_statements(sql):
        return SQLValidationResult(
            False,
            reason="Multiple SQL statements are not allowed.",
            feedback_for_repair="Return exactly one SELECT statement.",
        )

    normalized = normalize_sql(sql)
    if not starts_readonly(normalized):
        return SQLValidationResult(
            False,
            reason="Only SELECT or read-only WITH queries are allowed.",
            feedback_for_repair="Use SELECT only.",
        )

    keyword = blocked_keyword(normalized)
    if keyword is not None:
        return SQLValidationResult(
            False,
            reason=f"Blocked SQL keyword: {keyword}.",
            feedback_for_repair=f"Remove blocked keyword '{keyword}' and use SELECT only.",
        )

    projected = _projected_identifiers(normalized)
    if "*" in projected:
        return SQLValidationResult(False, reason="SELECT * is not allowed.", feedback_for_repair="Select explicit safe columns only.")

    hidden_columns = tuple(sorted(projected.intersection(HIDDEN_OUTPUT_COLUMNS)))
    if hidden_columns:
        return SQLValidationResult(
            False,
            reason=f"Query selects hidden column(s): {', '.join(hidden_columns)}.",
            feedback_for_repair="Remove hidden user/internal columns and select only safe display fields.",
        )

    used_sources = extract_source_names(normalized)
    if not used_sources:
        return SQLValidationResult(
            False,
            reason="Query does not reference an allowed source.",
            feedback_for_repair="Use one allowlisted source from the schema context.",
        )

    for source in used_sources:
        if "." in source and source.split(".", 1)[0] in SYSTEM_SCHEMAS:
            return SQLValidationResult(
                False,
                reason=f"System schema access is not allowed: {source}.",
                used_sources=used_sources,
                feedback_for_repair="Do not query system schemas.",
            )

    allowed_by_name = {source.name.lower(): source for source in allowed_sources}
    unknown_sources = tuple(source for source in used_sources if source not in allowed_by_name)
    if unknown_sources:
        return SQLValidationResult(
            False,
            reason=f"Query references non-allowlisted source(s): {', '.join(unknown_sources)}.",
            used_sources=used_sources,
            feedback_for_repair="Use only allowlisted sources from the provided schema context.",
        )

    for source_name in used_sources:
        source = allowed_by_name[source_name]
        if not requires_user_id_check(source, normalized):
            return SQLValidationResult(
                False,
                reason=f"Source '{source.name}' requires a :user_id filter or function argument.",
                used_sources=used_sources,
                feedback_for_repair=f"Add the required :user_id filter or call {source.name}(:user_id).",
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
