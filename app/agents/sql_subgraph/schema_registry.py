"""Allowlisted SQL sources for the NexusOne SQL subgraph."""

from __future__ import annotations

from app.agents.sql_subgraph.state import SourceColumn, SourceDefinition


def cols(*items: tuple[str, str]) -> tuple[SourceColumn, ...]:
    return tuple(SourceColumn(name=name, description=description) for name, description in items)


SQL_SOURCE_REGISTRY: dict[str, SourceDefinition] = {
    "company_holidays": SourceDefinition(
        name="company_holidays",
        kind="table",
        domain="public_lookup",
        description="Company holidays by region and date.",
        access_roles="all_active",
        max_rows=50,
        columns=cols(
            ("region", "Country or regional office grouping."),
            ("holiday_name", "Holiday display name."),
            ("date", "Holiday date."),
            ("type", "Holiday type."),
            ("notes", "Short note about applicability."),
        ),
    ),
    "tool_directory": SourceDefinition(
        name="tool_directory",
        kind="table",
        domain="public_lookup",
        description="Internal tools, owners, support teams, and access methods.",
        access_roles="all_active",
        max_rows=50,
        columns=cols(
            ("name", "Tool display name."),
            ("owner_department", "Owning department."),
            ("access_method", "How employees request or use the tool."),
            ("support_team", "Support team for the tool."),
        ),
    ),
    "office_locations": SourceDefinition(
        name="office_locations",
        kind="table",
        domain="public_lookup",
        description="NexusOne office locations.",
        access_roles="all_active",
        max_rows=50,
        columns=cols(
            ("country", "Office country."),
            ("city", "Office city."),
            ("address", "Office address."),
            ("timezone", "Office timezone."),
        ),
    ),
    "active_employee_directory_public": SourceDefinition(
        name="active_employee_directory_public",
        kind="view",
        domain="public_lookup",
        description="Safe employee directory view for active users.",
        access_roles="all_active",
        max_rows=50,
        columns=cols(
            ("name", "Employee name."),
            ("email", "Employee email."),
            ("department", "Employee department."),
            ("title", "Employee title."),
            ("location", "Employee location."),
        ),
    ),
    "project_status_public": SourceDefinition(
        name="project_status_public",
        kind="table",
        domain="project_public",
        description="Public project status summaries.",
        access_roles="all_active",
        max_rows=25,
        columns=cols(
            ("project_id", "Project identifier."),
            ("name", "Project name."),
            ("department", "Owning department."),
            ("status", "Current public status."),
            ("public_summary", "Approved public internal summary."),
            ("last_updated", "Last update date."),
        ),
    ),
    "accessible_tickets": SourceDefinition(
        name="accessible_tickets",
        kind="function",
        domain="ticket_status",
        description=(
            "Ticket rows filtered by can_user_access_ticket for the current user: "
            "creator-owned rows for ordinary users and policy-authorized assigned rows for queue roles."
        ),
        access_roles="all_active",
        max_rows=25,
        requires_user_id=True,
        sensitive=True,
        columns=cols(
            ("ticket_id", "Ticket identifier."),
            ("department", "Ticket queue department."),
            ("category", "Ticket category."),
            ("priority", "Ticket priority."),
            ("status", "Ticket status."),
            ("created_at", "Creation timestamp."),
            ("updated_at", "Update timestamp."),
            ("visibility_scope", "Ticket visibility scope."),
        ),
    ),
    "accessible_ticket_events": SourceDefinition(
        name="accessible_ticket_events",
        kind="function",
        domain="ticket_status",
        description=(
            "Ticket event rows filtered through the same can_user_access_ticket predicate "
            "used for creator and authorized assignment visibility."
        ),
        access_roles="all_active",
        max_rows=50,
        requires_user_id=True,
        sensitive=True,
        columns=cols(
            ("ticket_id", "Ticket identifier."),
            ("event_type", "Event type."),
            ("event_text", "Event text."),
            ("created_at", "Event timestamp."),
        ),
    ),
    "accessible_ticket_assignments": SourceDefinition(
        name="accessible_ticket_assignments",
        kind="function",
        domain="ticket_status",
        description=(
            "Safe ticket assignment display rows filtered through can_user_access_ticket; "
            "assignment scope is enforced server-side before names are joined."
        ),
        access_roles="all_active",
        max_rows=25,
        requires_user_id=True,
        sensitive=True,
        columns=cols(
            ("ticket_id", "Ticket identifier."),
            ("department", "Ticket queue department."),
            ("category", "Ticket category."),
            ("priority", "Ticket priority."),
            ("status", "Ticket status."),
            ("updated_at", "Update timestamp."),
            ("assignee_name", "Public display name for the assigned support person."),
            ("assignee_title", "Public job title for the assigned support person."),
            ("assignee_department", "Public department for the assigned support person."),
            ("support_team", "Support team display name."),
        ),
    ),
    "finance_summaries": SourceDefinition(
        name="finance_summaries",
        kind="table",
        domain="finance_summary",
        description="Finance metrics by period and department.",
        access_roles=("finance", "executive", "ceo"),
        max_rows=25,
        sensitive=True,
        columns=cols(
            ("period", "Finance period."),
            ("metric", "Metric name."),
            ("value", "Metric value."),
            ("unit", "Metric unit."),
            ("department", "Department when applicable."),
            ("notes", "Finance notes."),
        ),
    ),
    "department_budgets": SourceDefinition(
        name="department_budgets",
        kind="table",
        domain="finance_budget",
        description="Budget allocation, actual spend, forecast spend, variance, and risk by department.",
        access_roles=("finance", "executive", "ceo"),
        max_rows=25,
        sensitive=True,
        columns=cols(
            ("period", "Budget period."),
            ("department", "Department name."),
            ("allocated_budget", "Approved budget."),
            ("actual_spend", "Spend to date."),
            ("forecast_spend", "Forecast final spend."),
            ("variance", "Forecast minus allocated budget."),
            ("risk_level", "Budget risk label."),
        ),
    ),
    "vendor_payment_aging": SourceDefinition(
        name="vendor_payment_aging",
        kind="table",
        domain="vendor_aging",
        description="Vendor payment aging and overdue payment status.",
        access_roles=("finance", "executive", "ceo"),
        max_rows=25,
        sensitive=True,
        columns=cols(
            ("vendor_id", "Vendor identifier."),
            ("vendor_name", "Vendor name."),
            ("amount_due", "Amount due."),
            ("days_overdue", "Days overdue."),
            ("status", "Payment status."),
        ),
    ),
    "revenue_risks": SourceDefinition(
        name="revenue_risks",
        kind="table",
        domain="finance_revenue_risk",
        description="Executive revenue risk rows by account segment.",
        access_roles=("executive", "ceo"),
        max_rows=25,
        sensitive=True,
        columns=cols(
            ("risk_id", "Risk identifier."),
            ("period", "Risk period."),
            ("account_segment", "Account segment."),
            ("risk_type", "Risk type."),
            ("revenue_at_risk", "Revenue amount at risk."),
            ("probability", "Risk probability."),
            ("mitigation", "Mitigation summary."),
        ),
    ),
    "benefits_vendors": SourceDefinition(
        name="benefits_vendors",
        kind="table",
        domain="hr_lifecycle",
        description="HR benefits vendor matrix.",
        access_roles=("hr", "executive", "ceo"),
        max_rows=25,
        sensitive=True,
        columns=cols(
            ("vendor_name", "Vendor name."),
            ("benefit_type", "Benefit type."),
            ("region", "Covered region."),
            ("renewal_date", "Renewal date."),
            ("notes", "Vendor notes."),
        ),
    ),
    "headcount_plan": SourceDefinition(
        name="headcount_plan",
        kind="table",
        domain="hr_headcount",
        description="Planned and approved hires by department and quarter.",
        access_roles=("manager", "hr", "executive", "ceo"),
        max_rows=25,
        sensitive=True,
        columns=cols(
            ("department", "Department name."),
            ("planned_hires", "Planned hires."),
            ("approved_hires", "Approved hires."),
            ("open_roles", "Open roles summary."),
            ("quarter", "Planning quarter."),
            ("approval_status", "Approval status."),
        ),
    ),
    "employee_lifecycle_slas": SourceDefinition(
        name="employee_lifecycle_slas",
        kind="table",
        domain="hr_lifecycle",
        description="HR process SLA targets.",
        access_roles=("manager", "hr", "executive", "ceo"),
        max_rows=25,
        columns=cols(
            ("process_name", "Lifecycle process name."),
            ("owner_team", "Owner team."),
            ("sla_days", "SLA in days."),
        ),
    ),
    "project_status_executive": SourceDefinition(
        name="project_status_executive",
        kind="table",
        domain="project_executive",
        description="Executive project status including budget and delivery risk.",
        access_roles=("executive", "ceo"),
        max_rows=25,
        sensitive=True,
        columns=cols(
            ("project_id", "Project identifier."),
            ("name", "Project name."),
            ("status", "Current status."),
            ("budget_risk", "Budget risk label."),
            ("delivery_risk", "Delivery risk label."),
            ("customer_impact", "Customer impact summary."),
        ),
    ),
    "user_accessible_documents": SourceDefinition(
        name="user_accessible_documents",
        kind="view",
        domain="document_metadata",
        description="Document metadata filtered to documents the user can access.",
        access_roles="all_active",
        max_rows=50,
        requires_user_id=True,
        columns=cols(
            ("doc_id", "Document id."),
            ("title", "Document title."),
            ("source_type", "Source type."),
            ("department", "Owning department."),
        ),
    ),
}


INTENT_SOURCE_NAMES: dict[str, tuple[str, ...]] = {
    "public_lookup": (
        "company_holidays",
        "tool_directory",
        "office_locations",
        "active_employee_directory_public",
        "project_status_public",
    ),
    "ticket_status": ("accessible_tickets", "accessible_ticket_events", "accessible_ticket_assignments"),
    "finance_summary": ("finance_summaries",),
    "finance_budget": ("department_budgets",),
    "finance_revenue_risk": ("revenue_risks",),
    "vendor_aging": ("vendor_payment_aging",),
    "hr_headcount": ("headcount_plan",),
    "hr_lifecycle": ("employee_lifecycle_slas", "benefits_vendors"),
    "project_public": ("project_status_public",),
    "project_executive": ("project_status_executive",),
    "document_metadata": ("user_accessible_documents",),
}


def get_source(name: str) -> SourceDefinition:
    return SQL_SOURCE_REGISTRY[name]


def sources_for_intent(intent: str) -> tuple[SourceDefinition, ...]:
    return tuple(SQL_SOURCE_REGISTRY[name] for name in INTENT_SOURCE_NAMES.get(intent, ()))
