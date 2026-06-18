"""User-facing presentation helpers for SQL subgraph results."""

from __future__ import annotations

from typing import Any, Mapping

from app.agents.sql_subgraph.state import SQLSubgraphOutput


HIDDEN_USER_REFERENCE_COLUMNS = {
    "requester_id",
    "assigned_to",
    "actor_user_id",
    "manager_id",
    "admin_contact",
    "escalation_contact",
    "owner",
    "user_id",
}

HIDDEN_INTERNAL_COLUMNS = {
    "confidentiality",
    "source_path",
    "docs_path",
}

DOMAIN_ALLOWED_COLUMNS = {
    "ticket_status": {
        "ticket_id",
        "department",
        "category",
        "priority",
        "status",
        "updated_at",
        "event_type",
        "event_text",
        "created_at",
    },
    "public_lookup": {
        "region",
        "holiday_name",
        "date",
        "type",
        "notes",
        "name",
        "owner_department",
        "access_method",
        "support_team",
        "country",
        "city",
        "address",
        "timezone",
        "email",
        "department",
        "title",
        "status",
        "public_summary",
        "last_updated",
    },
    "project_public": {"project_id", "name", "department", "status", "public_summary", "last_updated"},
    "project_executive": {"project_id", "name", "status", "budget_risk", "delivery_risk", "customer_impact"},
    "finance_budget": {
        "period",
        "department",
        "allocated_budget",
        "actual_spend",
        "forecast_spend",
        "variance",
        "risk_level",
    },
    "finance_summary": {"period", "metric", "value", "unit", "department", "notes"},
    "finance_revenue_risk": {
        "risk_id",
        "period",
        "account_segment",
        "risk_type",
        "revenue_at_risk",
        "probability",
        "mitigation",
    },
    "vendor_aging": {"vendor_id", "vendor_name", "amount_due", "days_overdue", "status"},
    "hr_headcount": {"department", "planned_hires", "approved_hires", "open_roles", "quarter", "approval_status"},
    "hr_lifecycle": {"process_name", "owner_team", "sla_days", "vendor_name", "benefit_type", "region", "renewal_date", "notes"},
    "document_metadata": {"doc_id", "title", "source_type", "department"},
}


def output_domain(output: SQLSubgraphOutput) -> str | None:
    if not output.sql_sources:
        return None
    first_source = output.sql_sources[0]
    domain = first_source.get("domain")
    return str(domain) if domain else None


def sanitize_row(row: Mapping[str, Any], domain: str | None) -> dict[str, Any]:
    allowed_columns = DOMAIN_ALLOWED_COLUMNS.get(domain or "", set())
    sanitized: dict[str, Any] = {}
    for key, value in row.items():
        if key in HIDDEN_USER_REFERENCE_COLUMNS or key in HIDDEN_INTERNAL_COLUMNS:
            continue
        if allowed_columns and key not in allowed_columns:
            continue
        sanitized[key] = value
    return sanitized


def sanitized_rows(output: SQLSubgraphOutput) -> list[dict[str, Any]]:
    domain = output_domain(output)
    return [sanitize_row(row, domain) for row in output.sql_rows]


def sanitized_columns(output: SQLSubgraphOutput) -> list[str]:
    rows = sanitized_rows(output)
    if rows:
        return list(rows[0].keys())
    domain = output_domain(output)
    allowed_columns = DOMAIN_ALLOWED_COLUMNS.get(domain or "", set())
    return [column for column in output.sql_columns if column in allowed_columns]


def safe_summary_payload(question: str, output: SQLSubgraphOutput) -> dict[str, Any]:
    return {
        "question": question,
        "status": output.sql_status,
        "summary": output.sql_answer_summary,
        "columns": sanitized_columns(output),
        "rows": sanitized_rows(output),
    }


def format_safe_terminal_answer(output: SQLSubgraphOutput) -> str:
    if output.sql_denied_reason:
        return f"Denied: {output.sql_denied_reason}"
    if output.sql_error:
        return f"Error: {output.sql_error}"
    if not output.sql_rows:
        return output.sql_answer_summary

    rows = sanitized_rows(output)
    domain = output_domain(output)
    if domain == "ticket_status":
        if len(rows) == 1:
            row = rows[0]
            parts = [f"Ticket {row.get('ticket_id')} is {row.get('status')}"]
            if row.get("updated_at") is not None:
                parts.append(f"Last updated {row['updated_at']}")
            if row.get("priority") is not None:
                parts.append(f"Priority {row['priority']}")
            return ". ".join(parts) + "."
        lines = [f"I found {len(rows)} accessible ticket(s):"]
        for row in rows:
            lines.append(
                "- "
                f"{row.get('ticket_id')}: {row.get('status')} "
                f"({row.get('department')}, {row.get('category')}, priority {row.get('priority')}, "
                f"updated {row.get('updated_at')})"
            )
        return "\n".join(lines)

    lines = [output.sql_answer_summary]
    for row in rows:
        lines.append(f"- {row}")
    return "\n".join(lines)
