-- Load synthetic CSV seed/source data.
-- Files are mounted by docker-compose.yml at /seed/csv.

BEGIN;

COPY users (
    user_id,
    name,
    email,
    role,
    department,
    title,
    manager_id,
    location,
    status
)
FROM '/seed/csv/public/users_seed.csv'
WITH (FORMAT csv, HEADER true);

COPY "groups" (
    group_name,
    description
)
FROM '/seed/csv/public/groups_seed.csv'
WITH (FORMAT csv, HEADER true);

COPY departments (
    department_id,
    name,
    head_user_id
)
FROM '/seed/csv/public/departments_seed.csv'
WITH (FORMAT csv, HEADER true);

COPY user_groups (
    user_id,
    group_name
)
FROM '/seed/csv/public/user_groups_seed.csv'
WITH (FORMAT csv, HEADER true);

INSERT INTO employee_directory (
    user_id,
    name,
    email,
    department,
    title,
    manager_id,
    location,
    start_date,
    visibility
)
SELECT
    user_id,
    name,
    email,
    department,
    title,
    manager_id,
    location,
    DATE '2026-01-01' + ((substring(user_id from 2)::integer - 1) * 7),
    'public_internal'
FROM users
ON CONFLICT (user_id) DO UPDATE SET
    name = EXCLUDED.name,
    email = EXCLUDED.email,
    department = EXCLUDED.department,
    title = EXCLUDED.title,
    manager_id = EXCLUDED.manager_id,
    location = EXCLUDED.location,
    start_date = EXCLUDED.start_date,
    visibility = EXCLUDED.visibility;

COPY company_holidays (
    holiday_id,
    region,
    holiday_name,
    date,
    type,
    notes
)
FROM '/seed/csv/public/company_holidays_2026.csv'
WITH (FORMAT csv, HEADER true);

COPY tool_directory (
    tool_id,
    name,
    owner_department,
    access_method,
    support_team,
    docs_path
)
FROM '/seed/csv/public/tool_directory.csv'
WITH (FORMAT csv, HEADER true);

COPY office_locations (
    office_id,
    country,
    city,
    address,
    timezone,
    admin_contact
)
FROM '/seed/csv/public/office_locations.csv'
WITH (FORMAT csv, HEADER true);

COPY tickets (
    ticket_id,
    requester_id,
    department,
    category,
    priority,
    status,
    assigned_to,
    created_at,
    updated_at,
    description,
    visibility_scope
)
FROM '/seed/csv/it/it_tickets_seed.csv'
WITH (FORMAT csv, HEADER true);

COPY tickets (
    ticket_id,
    requester_id,
    department,
    category,
    priority,
    status,
    assigned_to,
    created_at,
    updated_at,
    description,
    visibility_scope
)
FROM '/seed/csv/hr/hr_tickets_seed.csv'
WITH (FORMAT csv, HEADER true);

COPY tickets (
    ticket_id,
    requester_id,
    department,
    category,
    priority,
    status,
    assigned_to,
    created_at,
    updated_at,
    description,
    visibility_scope
)
FROM '/seed/csv/admin/admin_tickets_seed.csv'
WITH (FORMAT csv, HEADER true);

COPY tickets (
    ticket_id,
    requester_id,
    department,
    category,
    priority,
    status,
    assigned_to,
    created_at,
    updated_at,
    description,
    visibility_scope
)
FROM '/seed/csv/finance/finance_tickets_seed.csv'
WITH (FORMAT csv, HEADER true);

INSERT INTO ticket_events (
    ticket_id,
    actor_user_id,
    event_type,
    event_text,
    created_at
)
SELECT
    ticket_id,
    requester_id,
    'created',
    'Seed ticket created from synthetic setup CSV',
    created_at
FROM tickets;

COPY finance_summaries (
    period,
    metric,
    value,
    unit,
    department,
    confidentiality,
    notes
)
FROM '/seed/csv/finance/finance_q4_summary.csv'
WITH (FORMAT csv, HEADER true);

COPY department_budgets (
    period,
    department,
    allocated_budget,
    actual_spend,
    forecast_spend,
    variance,
    risk_level,
    confidentiality
)
FROM '/seed/csv/finance/department_budget_2026.csv'
WITH (FORMAT csv, HEADER true);

COPY revenue_risks (
    risk_id,
    period,
    account_segment,
    risk_type,
    revenue_at_risk,
    probability,
    owner,
    mitigation,
    confidentiality
)
FROM '/seed/csv/finance/revenue_risk_register_q4_2025.csv'
WITH (FORMAT csv, HEADER true);

COPY vendor_payment_aging (
    vendor_id,
    vendor_name,
    amount_due,
    days_overdue,
    owner,
    status
)
FROM '/seed/csv/finance/vendor_payment_aging_q1_2026.csv'
WITH (FORMAT csv, HEADER true);

COPY benefits_vendors (
    vendor_name,
    benefit_type,
    region,
    contact,
    renewal_date,
    notes
)
FROM '/seed/csv/hr/benefits_vendor_matrix.csv'
WITH (FORMAT csv, HEADER true);

COPY headcount_plan (
    department,
    planned_hires,
    approved_hires,
    open_roles,
    quarter,
    approval_status
)
FROM '/seed/csv/hr/headcount_plan_2026.csv'
WITH (FORMAT csv, HEADER true);

COPY employee_lifecycle_slas (
    process_name,
    owner_team,
    sla_days,
    escalation_contact
)
FROM '/seed/csv/hr/employee_lifecycle_sla.csv'
WITH (FORMAT csv, HEADER true);

COPY project_status_public (
    project_id,
    name,
    department,
    status,
    public_summary,
    last_updated
)
FROM '/seed/csv/public/project_status_public.csv'
WITH (FORMAT csv, HEADER true);

COPY project_status_executive (
    project_id,
    name,
    status,
    budget_risk,
    delivery_risk,
    customer_impact,
    owner
)
FROM '/seed/csv/executive/project_status_executive.csv'
WITH (FORMAT csv, HEADER true);

COMMIT;
