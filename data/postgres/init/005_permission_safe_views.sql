-- Permission-safe structured data access helpers for the SQL subgraph.
-- These helpers are for synthetic local development data only.
-- Every ticket list, detail, event, and assignment path delegates to the same
-- server-owned can_user_access_ticket predicate from 001_schema.sql. The raw
-- requester/assignee columns are internal function output only; the planner
-- registry and presentation layer keep them out of model/API payloads.

BEGIN;

CREATE OR REPLACE VIEW active_employee_directory_public AS
SELECT
    ed.user_id,
    ed.name,
    ed.email,
    ed.department,
    ed.title,
    ed.manager_id,
    ed.location
FROM employee_directory ed
JOIN users u ON u.user_id = ed.user_id
WHERE u.status = 'active'
  AND ed.visibility = 'public_internal';

CREATE OR REPLACE FUNCTION accessible_tickets(p_user_id text)
RETURNS TABLE (
    ticket_id text,
    requester_id text,
    department text,
    category text,
    priority text,
    status text,
    assigned_to text,
    created_at timestamptz,
    updated_at timestamptz,
    visibility_scope text
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        t.ticket_id,
        t.requester_id,
        t.department,
        t.category,
        t.priority,
        t.status,
        t.assigned_to,
        t.created_at,
        t.updated_at,
        t.visibility_scope
    FROM tickets t
    WHERE can_user_access_ticket(p_user_id, t.ticket_id);
$$;

CREATE OR REPLACE FUNCTION accessible_ticket_events(p_user_id text)
RETURNS TABLE (
    event_id bigint,
    ticket_id text,
    actor_user_id text,
    event_type text,
    event_text text,
    created_at timestamptz
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        te.event_id,
        te.ticket_id,
        te.actor_user_id,
        te.event_type,
        te.event_text,
        te.created_at
    FROM ticket_events te
    WHERE can_user_access_ticket(p_user_id, te.ticket_id);
$$;

CREATE OR REPLACE FUNCTION accessible_ticket_assignments(p_user_id text)
RETURNS TABLE (
    ticket_id text,
    department text,
    category text,
    priority text,
    status text,
    updated_at timestamptz,
    assignee_name text,
    assignee_title text,
    assignee_department text,
    support_team text
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        t.ticket_id,
        t.department,
        t.category,
        t.priority,
        t.status,
        t.updated_at,
        ed.name AS assignee_name,
        ed.title AS assignee_title,
        ed.department AS assignee_department,
        CASE t.department
            WHEN 'it' THEN 'IT Support'
            WHEN 'hr' THEN 'HR Operations'
            WHEN 'admin' THEN 'Admin Operations'
            WHEN 'finance' THEN 'Finance Operations'
            ELSE 'Support'
        END AS support_team
    FROM tickets t
    LEFT JOIN employee_directory ed
        ON ed.user_id = t.assigned_to
       AND ed.visibility = 'public_internal'
    WHERE can_user_access_ticket(p_user_id, t.ticket_id);
$$;

COMMIT;
