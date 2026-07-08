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
        "assignee_name",
        "assignee_title",
        "assignee_department",
        "support_team",
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


def _is_assignment_question(question: str | None) -> bool:
    if not question:
        return False
    lowered = question.lower()
    return any(
        term in lowered
        for term in (
            "assigned",
            "assignee",
            "handling",
            "handler",
            "responsible",
            "who is working",
            "who's working",
            "working on",
            "taking care",
        )
    )


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


def _format_assignment_row(row: Mapping[str, Any]) -> str:
    ticket = row.get("ticket_id")
    assignee = row.get("assignee_name") or row.get("support_team")
    if not assignee:
        status = row.get("status")
        if ticket and status:
            return f"I cannot show internal assignee/requester identifiers. Ticket {ticket} is {status}."
        return "I cannot show internal assignee/requester identifiers."

    title = row.get("assignee_title")
    department = row.get("assignee_department")
    identity = str(assignee)
    if title and department:
        identity = f"{identity} ({title}, {department})"
    elif title:
        identity = f"{identity} ({title})"

    parts = [f"Ticket {ticket} is assigned to {identity}"]
    if row.get("updated_at") is not None:
        parts.append(f"Last updated {row['updated_at']}")
    if row.get("priority") is not None:
        parts.append(f"Priority {row['priority']}")
    if row.get("status") is not None:
        parts.append(f"Status {row['status']}")
    return ". ".join(parts) + "."


def _format_ticket_row(row: Mapping[str, Any]) -> str:
    ticket = row.get("ticket_id")
    status = row.get("status")
    if ticket and status:
        parts = [f"Ticket {ticket} is {status}"]
    elif ticket:
        parts = [f"Ticket {ticket} matched the request"]
    else:
        parts = ["A matching ticket was found"]
    if row.get("updated_at") is not None:
        parts.append(f"Last updated {row['updated_at']}")
    if row.get("priority") is not None:
        parts.append(f"Priority {row['priority']}")
    return ". ".join(parts) + "."


def _format_public_lookup_rows(rows: list[dict[str, Any]], summary: str) -> str:
    if not rows:
        return summary
    lines = [summary]
    for row in rows:
        if row.get("holiday_name"):
            details = [str(row["holiday_name"])]
            if row.get("date") is not None:
                details.append(str(row["date"]))
            if row.get("region") is not None:
                details.append(str(row["region"]))
            if row.get("notes") is not None:
                details.append(str(row["notes"]))
            lines.append("- " + " - ".join(details))
            continue
        label = row.get("name") or row.get("city") or row.get("country") or row.get("project_id")
        if label:
            details = [str(label)]
            for key in ("department", "title", "status", "public_summary", "last_updated"):
                if row.get(key) is not None:
                    details.append(str(row[key]))
            lines.append("- " + " - ".join(details))
            continue
        lines.append("- " + ", ".join(f"{key}: {value}" for key, value in row.items()))
    return "\n".join(lines)


def format_safe_terminal_answer(output: SQLSubgraphOutput, question: str | None = None) -> str:
    if output.sql_denied_reason:
        return f"Denied: {output.sql_denied_reason}"
    if output.sql_error:
        return f"Error: {output.sql_error}"

    rows = sanitized_rows(output)
    domain = output_domain(output)
    if domain == "ticket_status":
        if not rows:
            if question and any(char.isdigit() for char in question):
                return "I could not find an accessible matching ticket."
            return output.sql_answer_summary
        if _is_assignment_question(question):
            return _format_assignment_row(rows[0])
        if len(rows) == 1:
            return _format_ticket_row(rows[0])
        lines = [f"I found {len(rows)} accessible ticket(s):"]
        for row in rows:
            details = []
            for key in ("department", "category"):
                if row.get(key) is not None:
                    details.append(str(row[key]))
            if row.get("priority") is not None:
                details.append(f"priority {row['priority']}")
            if row.get("updated_at") is not None:
                details.append(f"updated {row['updated_at']}")
            suffix = f" ({', '.join(details)})" if details else ""
            lines.append(f"- {row.get('ticket_id')}: {row.get('status')}{suffix}")
        return "\n".join(lines)

    if domain == "public_lookup":
        return _format_public_lookup_rows(rows, output.sql_answer_summary)

    if not rows:
        return output.sql_answer_summary
    lines = [output.sql_answer_summary]
    for row in rows:
        lines.append(f"- {row}")
    return "\n".join(lines)
