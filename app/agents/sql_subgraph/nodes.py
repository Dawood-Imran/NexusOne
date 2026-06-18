"""Deterministic nodes for the independent SQL subgraph."""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.agents.sql_subgraph.permissions import describe_denial, select_allowed_sources
from app.agents.sql_subgraph.result_formatting import (
    format_error,
    format_execution_output,
    format_refusal,
    format_validated_output,
)
from app.agents.sql_subgraph.sql_validator import validate_sql
from app.agents.sql_subgraph.state import SQLExecutor, SQLPlanner, SQLSubgraphOutput, SQLSubgraphState, UserContext
from app.agents.sql_subgraph.tools import sql_execute_readonly, sql_get_schema_context


KNOWN_INTENTS = {
    "public_lookup",
    "ticket_status",
    "finance_summary",
    "finance_budget",
    "finance_revenue_risk",
    "vendor_aging",
    "hr_headcount",
    "hr_lifecycle",
    "project_public",
    "project_executive",
    "document_metadata",
}


def load_user_context(state: SQLSubgraphState, executor: SQLExecutor | None = None) -> SQLSubgraphState:
    if state.user_context is not None:
        return state
    if executor is None:
        state.output = format_refusal("User context is required when no database executor is provided.")
        state.sql_status = state.output.sql_status
        return state

    row = executor.fetch_one(
        """
        SELECT
            u.user_id,
            u.role,
            u.department,
            u.location,
            u.status,
            COALESCE(array_agg(ug.group_name) FILTER (WHERE ug.group_name IS NOT NULL), '{}') AS groups
        FROM users u
        LEFT JOIN user_groups ug ON ug.user_id = u.user_id
        WHERE u.user_id = :user_id
        GROUP BY u.user_id
        """,
        {"user_id": state.user_id},
    )
    if row is None:
        state.output = format_refusal("User does not exist or cannot be loaded.")
        state.sql_status = state.output.sql_status
        return state

    groups = row.get("groups") or ()
    state.user_context = UserContext(
        user_id=str(row["user_id"]),
        role=str(row["role"]),
        department=str(row["department"]),
        location=str(row["location"]),
        status=str(row["status"]),
        groups=tuple(groups),
    )
    return state


def _heuristic_classify_sql_intent(state: SQLSubgraphState) -> SQLSubgraphState:
    requested = (state.requested_intent or "").strip()
    if requested in KNOWN_INTENTS:
        state.sql_intent = requested  # type: ignore[assignment]
        return state

    question = state.question.lower()
    if any(term in question for term in ("ticket", "case", "request status", "queue")):
        state.sql_intent = "ticket_status"
    elif any(term in question for term in ("holiday", "holidays", "office closed")):
        state.sql_intent = "public_lookup"
    elif any(term in question for term in ("tool", "tools", "office", "location", "employee directory", "who is")):
        state.sql_intent = "public_lookup"
    elif any(term in question for term in ("vendor", "overdue", "payment aging")):
        state.sql_intent = "vendor_aging"
    elif any(term in question for term in ("budget", "utilization", "spend", "variance")):
        state.sql_intent = "finance_budget"
    elif any(term in question for term in ("revenue risk", "risk register", "revenue at risk")):
        state.sql_intent = "finance_revenue_risk"
    elif any(term in question for term in ("finance summary", "finance summaries", "q4 finance")):
        state.sql_intent = "finance_summary"
    elif any(term in question for term in ("headcount", "hiring plan", "planned hires", "approved hires")):
        state.sql_intent = "hr_headcount"
    elif any(term in question for term in ("benefit", "lifecycle", "sla", "onboarding sla")):
        state.sql_intent = "hr_lifecycle"
    elif "executive project" in question or ("project" in question and "risk" in question):
        state.sql_intent = "project_executive"
    elif "project" in question:
        state.sql_intent = "project_public"
    elif any(term in question for term in ("document", "docs", "source", "permission")):
        state.sql_intent = "document_metadata"
    else:
        state.sql_intent = "ambiguous"
    return state


def classify_sql_intent(state: SQLSubgraphState, planner: SQLPlanner | None = None) -> SQLSubgraphState:
    requested = (state.requested_intent or "").strip()
    if requested in KNOWN_INTENTS:
        state.sql_intent = requested  # type: ignore[assignment]
        return state

    if planner is not None:
        try:
            state.sql_intent = planner.classify_intent(state.question, state.requested_intent, KNOWN_INTENTS)
            return state
        except Exception as exc:  # noqa: BLE001 - fall back to deterministic classifier.
            state.error_message = f"Planner intent classification failed: {type(exc).__name__}"

    return _heuristic_classify_sql_intent(state)


def select_sources(state: SQLSubgraphState) -> SQLSubgraphState:
    if state.user_context is None or state.sql_intent is None:
        return state
    if state.sql_intent in ("unsupported", "ambiguous"):
        state.output = format_refusal(
            "The structured-data request needs clarification before SQL can be generated.",
            status="needs_clarification",
        )
        state.sql_status = state.output.sql_status
        return state

    state.allowed_sources = select_allowed_sources(state.user_context, state.sql_intent)
    if not state.allowed_sources:
        state.output = format_refusal(
            describe_denial(state.user_context, state.sql_intent),
            status="no_allowed_source",
        )
        state.sql_status = state.output.sql_status
    return state


def build_schema_context(state: SQLSubgraphState) -> SQLSubgraphState:
    state.schema_context = sql_get_schema_context(state.allowed_sources)
    return state


def _source_ref(source_name: str) -> str:
    if source_name in {"accessible_tickets", "accessible_ticket_events"}:
        return f"{source_name}(:user_id)"
    return source_name


def _detect_region(question: str) -> str | None:
    lowered = question.lower()
    known_regions = {
        "pakistan": "Pakistan",
        "united states": "United States",
        "usa": "United States",
        "us": "United States",
        "india": "India",
        "uk": "United Kingdom",
        "united kingdom": "United Kingdom",
    }
    for needle, region in known_regions.items():
        if re.search(rf"\b{re.escape(needle)}\b", lowered):
            return region
    return None


def _detect_ticket_id(question: str) -> str | None:
    match = re.search(r"\b[A-Z]{2,5}-\d{3,6}\b", question.upper())
    return match.group(0) if match else None


def _heuristic_draft_sql(state: SQLSubgraphState) -> SQLSubgraphState:
    if state.sql_intent is None or not state.allowed_sources:
        return state

    params: dict[str, Any] = {"user_id": state.user_id}
    question = state.question.lower()

    if state.sql_intent == "public_lookup":
        if "holiday" in question:
            region = _detect_region(state.question)
            if region:
                params["region"] = region
                state.candidate_sql = (
                    "SELECT region, holiday_name, date, type, notes "
                    "FROM company_holidays "
                    "WHERE region = :region "
                    "ORDER BY date ASC LIMIT 50"
                )
            else:
                state.candidate_sql = (
                    "SELECT region, holiday_name, date, type, notes "
                    "FROM company_holidays ORDER BY date ASC LIMIT 50"
                )
        elif "office" in question or "location" in question:
            state.candidate_sql = (
                "SELECT country, city, address, timezone "
                "FROM office_locations ORDER BY country, city LIMIT 50"
            )
        elif "tool" in question:
            state.candidate_sql = (
                "SELECT name, owner_department, access_method, support_team "
                "FROM tool_directory ORDER BY name LIMIT 50"
            )
        else:
            state.candidate_sql = (
                "SELECT project_id, name, department, status, public_summary, last_updated "
                "FROM project_status_public ORDER BY last_updated DESC LIMIT 25"
            )
    elif state.sql_intent == "ticket_status":
        ticket_id = _detect_ticket_id(state.question)
        if ticket_id:
            params["ticket_id"] = ticket_id
            state.candidate_sql = (
                "SELECT ticket_id, department, category, priority, status, updated_at "
                "FROM accessible_tickets(:user_id) WHERE ticket_id = :ticket_id "
                "ORDER BY updated_at DESC LIMIT 1"
            )
        else:
            state.candidate_sql = (
                "SELECT ticket_id, department, category, priority, status, updated_at "
                "FROM accessible_tickets(:user_id) ORDER BY updated_at DESC LIMIT 25"
            )
    elif state.sql_intent == "finance_budget":
        state.candidate_sql = (
            "SELECT period, department, allocated_budget, actual_spend, forecast_spend, variance, risk_level "
            "FROM department_budgets ORDER BY period DESC, department LIMIT 25"
        )
    elif state.sql_intent == "finance_summary":
        state.candidate_sql = (
            "SELECT period, metric, value, unit, department, notes "
            "FROM finance_summaries ORDER BY period DESC, metric LIMIT 25"
        )
    elif state.sql_intent == "finance_revenue_risk":
        state.candidate_sql = (
            "SELECT risk_id, period, account_segment, risk_type, revenue_at_risk, probability, mitigation "
            "FROM revenue_risks ORDER BY revenue_at_risk DESC LIMIT 25"
        )
    elif state.sql_intent == "vendor_aging":
        state.candidate_sql = (
            "SELECT vendor_id, vendor_name, amount_due, days_overdue, status "
            "FROM vendor_payment_aging "
            "WHERE days_overdue > 0 OR status ILIKE '%overdue%' "
            "ORDER BY days_overdue DESC, amount_due DESC LIMIT 25"
        )
    elif state.sql_intent == "hr_headcount":
        state.candidate_sql = (
            "SELECT department, planned_hires, approved_hires, open_roles, quarter, approval_status "
            "FROM headcount_plan ORDER BY quarter, department LIMIT 25"
        )
    elif state.sql_intent == "hr_lifecycle":
        state.candidate_sql = (
            "SELECT process_name, owner_team, sla_days "
            "FROM employee_lifecycle_slas ORDER BY process_name LIMIT 25"
        )
    elif state.sql_intent == "project_executive":
        state.candidate_sql = (
            "SELECT project_id, name, status, budget_risk, delivery_risk, customer_impact "
            "FROM project_status_executive ORDER BY budget_risk DESC, delivery_risk DESC LIMIT 25"
        )
    elif state.sql_intent == "project_public":
        state.candidate_sql = (
            "SELECT project_id, name, department, status, public_summary, last_updated "
            "FROM project_status_public ORDER BY last_updated DESC LIMIT 25"
        )
    elif state.sql_intent == "document_metadata":
        state.candidate_sql = (
            "SELECT doc_id, title, source_type, department "
            "FROM user_accessible_documents WHERE user_id = :user_id "
            "ORDER BY title LIMIT 50"
        )

    if state.candidate_sql is None:
        source = state.allowed_sources[0]
        source_ref = _source_ref(source.name)
        selected_columns = ", ".join(source.column_names[: min(5, len(source.column_names))])
        state.candidate_sql = f"SELECT {selected_columns} FROM {source_ref} LIMIT {source.max_rows}"

    state.sql_parameters = params
    return state


def draft_sql(state: SQLSubgraphState, planner: SQLPlanner | None = None) -> SQLSubgraphState:
    if state.sql_intent is None or not state.allowed_sources:
        return state

    if planner is not None:
        try:
            sql, parameters = planner.draft_sql(
                question=state.question,
                intent=state.sql_intent,
                schema_context=state.schema_context,
                allowed_sources=state.allowed_sources,
                user_id=state.user_id,
            )
            state.candidate_sql = sql
            merged_parameters = dict(parameters)
            merged_parameters["user_id"] = state.user_id
            state.sql_parameters = merged_parameters
            return state
        except Exception as exc:  # noqa: BLE001 - fall back to deterministic SQL draft.
            state.error_message = f"Planner SQL draft failed: {type(exc).__name__}"

    return _heuristic_draft_sql(state)


def validate_candidate_sql(state: SQLSubgraphState) -> SQLSubgraphState:
    if state.candidate_sql is None:
        state.output = format_refusal("No SQL could be drafted.", status="needs_clarification")
        state.sql_status = state.output.sql_status
        return state
    state.validation = validate_sql(state.candidate_sql, state.allowed_sources)
    if not state.validation.is_safe:
        state.output = format_refusal(state.validation.reason or "SQL failed validation.")
        state.sql_status = state.output.sql_status
    return state


def execute_or_package(state: SQLSubgraphState, executor: SQLExecutor | None = None) -> SQLSubgraphState:
    if state.validation is None or not state.validation.is_safe:
        return state

    sql = state.validation.sql_to_execute
    if sql is None:
        state.output = format_error("Validated SQL was missing.")
        state.sql_status = state.output.sql_status
        return state

    used_sources = state.validation.used_sources
    if not state.execute or executor is None:
        state.output = format_validated_output(sql, state.sql_parameters, state.allowed_sources, used_sources)
        state.sql_status = state.output.sql_status
        return state

    try:
        max_rows = min((source.max_rows for source in state.allowed_sources), default=25)
        result = sql_execute_readonly(executor, sql, state.sql_parameters, max_rows)
        state.execution_result = result
        state.output = format_execution_output(sql, state.sql_parameters, state.allowed_sources, used_sources, result)
        state.sql_status = state.output.sql_status
    except Exception as exc:  # noqa: BLE001 - package safe message, do not leak raw DB details to final answer.
        state.output = format_error(f"Database execution failed: {type(exc).__name__}")
        state.sql_status = state.output.sql_status
    return state


def ensure_output(state: SQLSubgraphState) -> SQLSubgraphOutput:
    if state.output is not None:
        return state.output
    return format_error("SQL subgraph finished without producing output.")
