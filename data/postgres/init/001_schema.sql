-- NexusOne Copilot local development schema.
-- This database is for synthetic setup data only. Do not load real company data.

BEGIN;

CREATE TABLE departments (
    department_id text PRIMARY KEY,
    name text NOT NULL UNIQUE,
    head_user_id text
);

CREATE TABLE users (
    user_id text PRIMARY KEY,
    name text NOT NULL,
    email text NOT NULL UNIQUE,
    role text NOT NULL CHECK (role IN (
        'employee',
        'manager',
        'hr',
        'finance',
        'it_admin',
        'admin_ops',
        'executive',
        'ceo'
    )),
    department text NOT NULL,
    title text,
    manager_id text REFERENCES users(user_id) DEFERRABLE INITIALLY DEFERRED,
    location text NOT NULL,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE departments
    ADD CONSTRAINT departments_head_user_id_fkey
    FOREIGN KEY (head_user_id) REFERENCES users(user_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE "groups" (
    group_name text PRIMARY KEY,
    description text NOT NULL
);

CREATE TABLE user_groups (
    user_id text NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    group_name text NOT NULL REFERENCES "groups"(group_name) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, group_name)
);

CREATE TABLE employee_directory (
    user_id text PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    name text NOT NULL,
    email text NOT NULL,
    department text NOT NULL,
    title text,
    manager_id text REFERENCES users(user_id) DEFERRABLE INITIALLY DEFERRED,
    location text NOT NULL,
    start_date date,
    visibility text NOT NULL DEFAULT 'public_internal'
);

CREATE TABLE permission_profiles (
    profile_name text PRIMARY KEY,
    confidentiality text NOT NULL CHECK (confidentiality IN (
        'public_internal',
        'department_internal',
        'manager_only',
        'hr_sensitive',
        'finance_sensitive',
        'it_sensitive',
        'executive',
        'ceo_only'
    )),
    description text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE permission_profile_grants (
    id bigserial PRIMARY KEY,
    profile_name text NOT NULL REFERENCES permission_profiles(profile_name) ON DELETE CASCADE,
    grant_type text NOT NULL CHECK (grant_type IN ('role', 'group', 'user')),
    grant_value text NOT NULL,
    UNIQUE (profile_name, grant_type, grant_value)
);

CREATE TABLE documents (
    doc_id text PRIMARY KEY,
    title text NOT NULL,
    source_type text NOT NULL CHECK (source_type IN ('pdf', 'markdown', 'csv', 'db')),
    source_path text NOT NULL UNIQUE,
    department text NOT NULL,
    permission_profile text REFERENCES permission_profiles(profile_name),
    confidentiality text NOT NULL CHECK (confidentiality IN (
        'public_internal',
        'department_internal',
        'manager_only',
        'hr_sensitive',
        'finance_sensitive',
        'it_sensitive',
        'executive',
        'ceo_only'
    )),
    created_at date NOT NULL DEFAULT CURRENT_DATE,
    updated_at date NOT NULL,
    canonical boolean NOT NULL DEFAULT true,
    generated boolean NOT NULL DEFAULT true,
    status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'draft')),
    key_topics text[] NOT NULL DEFAULT '{}'
);

CREATE TABLE document_permissions (
    id bigserial PRIMARY KEY,
    doc_id text NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    allowed_role text CHECK (allowed_role IN (
        'employee',
        'manager',
        'hr',
        'finance',
        'it_admin',
        'admin_ops',
        'executive',
        'ceo'
    )),
    allowed_group text REFERENCES "groups"(group_name) ON DELETE CASCADE,
    allowed_user_id text REFERENCES users(user_id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT document_permissions_exactly_one_grant
        CHECK (num_nonnulls(allowed_role, allowed_group, allowed_user_id) = 1),
    UNIQUE (doc_id, allowed_role),
    UNIQUE (doc_id, allowed_group),
    UNIQUE (doc_id, allowed_user_id)
);

CREATE TABLE document_chunks (
    chunk_id text PRIMARY KEY,
    doc_id text NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_index integer NOT NULL CHECK (chunk_index >= 0),
    page_number integer CHECK (page_number IS NULL OR page_number > 0),
    section_heading text,
    text_preview text NOT NULL,
    token_count integer NOT NULL CHECK (token_count >= 0),
    faiss_vector_id integer UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (doc_id, chunk_index)
);

CREATE TABLE tickets (
    ticket_id text PRIMARY KEY,
    requester_id text NOT NULL REFERENCES users(user_id),
    department text NOT NULL CHECK (department IN ('hr', 'it', 'admin', 'finance')),
    category text NOT NULL,
    priority text NOT NULL CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    status text NOT NULL CHECK (status IN (
        'open',
        'in_progress',
        'waiting_on_user',
        'resolved',
        'closed'
    )),
    assigned_to text REFERENCES users(user_id),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    description text NOT NULL,
    visibility_scope text NOT NULL DEFAULT 'own' CHECK (visibility_scope IN (
        'own',
        'department_queue',
        'manager_team'
    ))
);

CREATE TABLE ticket_events (
    event_id bigserial PRIMARY KEY,
    ticket_id text NOT NULL REFERENCES tickets(ticket_id) ON DELETE CASCADE,
    actor_user_id text REFERENCES users(user_id),
    event_type text NOT NULL CHECK (event_type IN (
        'created',
        'status_changed',
        'comment',
        'assigned',
        'priority_changed'
    )),
    event_text text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE company_holidays (
    holiday_id text PRIMARY KEY,
    region text NOT NULL,
    holiday_name text NOT NULL,
    date date NOT NULL,
    type text NOT NULL,
    notes text
);

CREATE TABLE tool_directory (
    tool_id text PRIMARY KEY,
    name text NOT NULL,
    owner_department text NOT NULL,
    access_method text NOT NULL,
    support_team text NOT NULL,
    docs_path text
);

CREATE TABLE office_locations (
    office_id text PRIMARY KEY,
    country text NOT NULL,
    city text NOT NULL,
    address text NOT NULL,
    timezone text NOT NULL,
    admin_contact text REFERENCES users(user_id)
);

CREATE TABLE finance_summaries (
    id bigserial PRIMARY KEY,
    period text NOT NULL,
    metric text NOT NULL,
    value numeric NOT NULL,
    unit text NOT NULL,
    department text,
    confidentiality text NOT NULL CHECK (confidentiality IN (
        'finance_sensitive',
        'executive',
        'ceo_only'
    )),
    notes text NOT NULL
);

CREATE TABLE department_budgets (
    id bigserial PRIMARY KEY,
    period text NOT NULL,
    department text NOT NULL,
    allocated_budget numeric NOT NULL,
    actual_spend numeric NOT NULL,
    forecast_spend numeric NOT NULL,
    variance numeric NOT NULL,
    risk_level text NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    confidentiality text NOT NULL CHECK (confidentiality IN (
        'finance_sensitive',
        'executive',
        'ceo_only'
    ))
);

CREATE TABLE revenue_risks (
    risk_id text PRIMARY KEY,
    period text NOT NULL,
    account_segment text NOT NULL,
    risk_type text NOT NULL,
    revenue_at_risk numeric NOT NULL,
    probability numeric NOT NULL CHECK (probability >= 0 AND probability <= 1),
    owner text REFERENCES users(user_id),
    mitigation text NOT NULL,
    confidentiality text NOT NULL CHECK (confidentiality IN ('executive', 'ceo_only'))
);

CREATE TABLE vendor_payment_aging (
    vendor_id text PRIMARY KEY,
    vendor_name text NOT NULL,
    amount_due numeric NOT NULL,
    days_overdue integer NOT NULL CHECK (days_overdue >= 0),
    owner text REFERENCES users(user_id),
    status text NOT NULL
);

CREATE TABLE benefits_vendors (
    id bigserial PRIMARY KEY,
    vendor_name text NOT NULL,
    benefit_type text NOT NULL,
    region text NOT NULL,
    contact text NOT NULL,
    renewal_date date NOT NULL,
    notes text,
    UNIQUE (vendor_name, benefit_type, region)
);

CREATE TABLE headcount_plan (
    id bigserial PRIMARY KEY,
    department text NOT NULL,
    planned_hires integer NOT NULL CHECK (planned_hires >= 0),
    approved_hires integer NOT NULL CHECK (approved_hires >= 0),
    open_roles text NOT NULL,
    quarter text NOT NULL,
    approval_status text NOT NULL
);

CREATE TABLE employee_lifecycle_slas (
    id bigserial PRIMARY KEY,
    process_name text NOT NULL UNIQUE,
    owner_team text NOT NULL,
    sla_days integer NOT NULL CHECK (sla_days >= 0),
    escalation_contact text REFERENCES users(user_id)
);

CREATE TABLE project_status_public (
    project_id text PRIMARY KEY,
    name text NOT NULL,
    department text NOT NULL,
    status text NOT NULL,
    public_summary text NOT NULL,
    last_updated date NOT NULL
);

CREATE TABLE project_status_executive (
    project_id text PRIMARY KEY,
    name text NOT NULL,
    status text NOT NULL,
    budget_risk text NOT NULL CHECK (budget_risk IN ('low', 'medium', 'high')),
    delivery_risk text NOT NULL CHECK (delivery_risk IN ('low', 'medium', 'high')),
    customer_impact text NOT NULL,
    owner text REFERENCES users(user_id)
);

CREATE TABLE ingestion_runs (
    ingestion_run_id bigserial PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    source_count integer NOT NULL DEFAULT 0 CHECK (source_count >= 0),
    chunk_count integer NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    error_message text
);

CREATE TABLE audit_logs (
    audit_id bigserial PRIMARY KEY,
    conversation_id text NOT NULL,
    turn_id text NOT NULL,
    user_id text REFERENCES users(user_id),
    role text,
    query text NOT NULL,
    intent text,
    retrieved_doc_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    allowed_doc_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    denied_doc_count integer NOT NULL DEFAULT 0 CHECK (denied_doc_count >= 0),
    tools_called jsonb NOT NULL DEFAULT '[]'::jsonb,
    final_answer_status text NOT NULL CHECK (final_answer_status IN (
        'answered',
        'refused',
        'needs_clarification',
        'error'
    )),
    model_used text,
    token_usage jsonb NOT NULL DEFAULT '{}'::jsonb,
    latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE feedback (
    feedback_id bigserial PRIMARY KEY,
    conversation_id text NOT NULL,
    turn_id text NOT NULL,
    user_id text REFERENCES users(user_id),
    rating text NOT NULL CHECK (rating IN (
        'helpful',
        'not_helpful',
        'incorrect',
        'missing_source',
        'outdated',
        'permission_issue'
    )),
    comment text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_department ON users(department);
CREATE INDEX idx_user_groups_group_name ON user_groups(group_name);

CREATE INDEX idx_documents_source_type ON documents(source_type);
CREATE INDEX idx_documents_permission_profile ON documents(permission_profile);
CREATE INDEX idx_documents_confidentiality ON documents(confidentiality);
CREATE INDEX idx_document_permissions_doc_id ON document_permissions(doc_id);
CREATE INDEX idx_document_permissions_role ON document_permissions(allowed_role);
CREATE INDEX idx_document_permissions_group ON document_permissions(allowed_group);
CREATE INDEX idx_document_permissions_user ON document_permissions(allowed_user_id);
CREATE INDEX idx_document_chunks_doc_id ON document_chunks(doc_id);
CREATE INDEX idx_document_chunks_faiss_vector_id ON document_chunks(faiss_vector_id);

CREATE INDEX idx_tickets_requester_id ON tickets(requester_id);
CREATE INDEX idx_tickets_department_status ON tickets(department, status);
CREATE INDEX idx_tickets_assigned_to ON tickets(assigned_to);
CREATE INDEX idx_ticket_events_ticket_id ON ticket_events(ticket_id);

CREATE INDEX idx_finance_summaries_period ON finance_summaries(period);
CREATE INDEX idx_department_budgets_period_department ON department_budgets(period, department);
CREATE INDEX idx_revenue_risks_period ON revenue_risks(period);
CREATE INDEX idx_project_status_public_status ON project_status_public(status);
CREATE INDEX idx_project_status_executive_risks ON project_status_executive(budget_risk, delivery_risk);
CREATE INDEX idx_audit_logs_user_created_at ON audit_logs(user_id, created_at);

CREATE OR REPLACE FUNCTION can_user_access_document(p_user_id text, p_doc_id text)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM users u
        JOIN documents d ON d.doc_id = p_doc_id
        WHERE u.user_id = p_user_id
          AND u.status = 'active'
          AND d.status = 'active'
          AND (
              EXISTS (
                  SELECT 1
                  FROM document_permissions dp
                  WHERE dp.doc_id = d.doc_id
                    AND dp.allowed_role = u.role
              )
              OR EXISTS (
                  SELECT 1
                  FROM document_permissions dp
                  JOIN user_groups ug
                    ON ug.user_id = u.user_id
                   AND ug.group_name = dp.allowed_group
                  WHERE dp.doc_id = d.doc_id
              )
              OR EXISTS (
                  SELECT 1
                  FROM document_permissions dp
                  WHERE dp.doc_id = d.doc_id
                    AND dp.allowed_user_id = u.user_id
              )
          )
    );
$$;

CREATE OR REPLACE FUNCTION can_user_access_ticket(p_user_id text, p_ticket_id text)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM users u
        JOIN tickets t ON t.ticket_id = p_ticket_id
        WHERE u.user_id = p_user_id
          AND u.status = 'active'
          AND (
              t.requester_id = u.user_id
              OR t.assigned_to = u.user_id
              OR u.role = 'ceo'
              OR (u.role = 'hr' AND t.department = 'hr')
              OR (u.role = 'finance' AND t.department = 'finance')
              OR (u.role = 'it_admin' AND t.department = 'it')
              OR (u.role = 'admin_ops' AND t.department = 'admin')
              OR (
                  u.role = 'manager'
                  AND EXISTS (
                      SELECT 1
                      FROM users report
                      WHERE report.manager_id = u.user_id
                        AND report.user_id = t.requester_id
                  )
              )
          )
    );
$$;

CREATE VIEW user_accessible_documents AS
SELECT
    u.user_id,
    d.doc_id,
    d.title,
    d.source_type,
    d.source_path,
    d.department,
    d.confidentiality
FROM users u
CROSS JOIN documents d
WHERE can_user_access_document(u.user_id, d.doc_id);

COMMIT;
