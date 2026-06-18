-- Permission-safe structured data access helpers for the SQL subgraph.
-- These helpers are for synthetic local development data only.

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

COMMIT;
