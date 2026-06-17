# NexusOne SQL Subgraph Implementation Plan

This folder is for the constrained SQL subgraph used by the NexusOne Copilot parent LangGraph workflow.

The SQL subgraph is responsible for exact structured-data answers from PostgreSQL. It should handle CSV-backed tables, ticket records, finance summaries, HR planning rows, public lookup tables, and permission-aware operational data. It is not the RAG path, and CSV rows should not be chunked into FAISS in the first implementation.

## Reference Docs Checked

- LangChain SQL agent tutorial: https://docs.langchain.com/oss/python/langchain/sql-agent
- LangGraph custom SQL agent tutorial: https://docs.langchain.com/oss/python/langgraph/sql-agent
- LangGraph subgraphs: https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- LangGraph conditional routing and parallel fan-out: https://docs.langchain.com/oss/python/langgraph/graph-api#conditional-edges

Important takeaway from the docs: the higher-level SQL agent is useful for understanding the workflow, but the tutorial's database tools are intentionally minimal demo wrappers. For NexusOne, we should implement a custom LangGraph SQL subgraph with deterministic safety gates before query execution.

## Goal

Build a custom LangGraph subgraph that:

1. Accepts a user question and user identity from the parent graph.
2. Loads the user's role, department, location, and groups from PostgreSQL.
3. Selects an allowlisted set of SQL sources based on user permissions and question intent.
4. Generates only read-only SQL using OpenAI through LangChain.
5. Validates generated SQL deterministically before execution.
6. Optionally runs an LLM query checker for SQL correctness after deterministic safety checks.
7. Executes only safe, read-only queries with enforced row limits.
8. Returns structured rows, safe source labels, used tables, and status metadata to the parent graph.
9. Never exposes unrestricted SQL access to the main assistant.

## Why Custom LangGraph Instead Of Prebuilt SQL Agent

Use a custom LangGraph subgraph, not the prebuilt SQL agent, for the first production-shaped implementation.

Reasons:

1. The LangChain tutorial's standard SQL agent relies heavily on prompting to make the model list tables, inspect schemas, check SQL, and avoid unsafe statements.
2. NexusOne has permission rules that must be enforced by code and database views/functions, not only by instructions in the prompt.
3. The parent graph needs deterministic outputs: rows, source labels, allowed table names, query status, denied access status, and validation errors.
4. We need a clean merge contract with the RAG subgraph when a question requires both document context and structured facts.
5. A custom subgraph makes retries, refusal, auditing, and future human review explicit nodes.

The prebuilt SQL agent pattern is still useful as a conceptual baseline:

```text
list tables -> inspect schema -> generate query -> check query -> execute query -> formulate answer
```

For NexusOne, that becomes:

```text
load user -> classify scope -> select allowed sources -> build safe schema context
-> draft SQL -> validate SQL -> check/repair SQL -> execute read-only SQL
-> package structured evidence -> return to parent graph
```

## Runtime Model

The SQL subgraph will use OpenAI through LangChain.

Configuration should be environment-driven:

```text
OPENAI_API_KEY
OPENAI_SQL_MODEL
OPENAI_SQL_TEMPERATURE=0
```

Do not hard-code the model name in graph logic. Use a config helper that reads `OPENAI_SQL_MODEL`, with a project-level default set later.

Recommended implementation shape:

```python
from langchain_openai import ChatOpenAI

sql_model = ChatOpenAI(
    model=settings.openai_sql_model,
    temperature=0,
)
```

Use temperature `0` for SQL generation and query checking because we want stable, reproducible SQL.

## Proposed Folder Contents

Target folder:

```text
app/agents/sql_subgraph/
  IMPLEMENTATION_PLAN.md
  __init__.py
  graph.py
  state.py
  nodes.py
  tools.py
  prompts.py
  schema_registry.py
  permissions.py
  sql_validator.py
  result_formatting.py
```

Supporting files outside this folder:

```text
app/core/settings.py
app/db/session.py
app/db/sql_readonly.py
data/postgres/init/005_permission_safe_views.sql
tests/unit/agents/sql_subgraph/test_sql_validator.py
tests/unit/agents/sql_subgraph/test_scope_selection.py
tests/integration/test_sql_subgraph_permissions.py
```

## Parent Graph Contract

The parent graph should not expose a raw SQL execution tool to the general assistant.

The parent graph should call the SQL subgraph when the intent router marks the question as:

- `structured_data`
- `ticket_status`
- `finance`
- `hr_structured`
- `public_lookup`
- `project_status`
- `mixed` with a SQL component

Parent input to SQL subgraph:

```python
class SQLSubgraphInput(TypedDict):
    conversation_id: str
    turn_id: str
    user_id: str
    question: str
    sql_question: str | None
    requested_intent: str | None
```

Parent output from SQL subgraph:

```python
class SQLSubgraphOutput(TypedDict):
    sql_status: Literal[
        "answered",
        "no_allowed_source",
        "needs_clarification",
        "refused",
        "error",
    ]
    sql_answer_summary: str
    sql_rows: list[dict]
    sql_columns: list[str]
    sql_sources: list[dict]
    sql_used_tables: list[str]
    sql_query_id: str | None
    sql_denied_reason: str | None
    sql_error: str | None
```

The parent graph should merge this into its main state under a dedicated field:

```python
sql_result: SQLSubgraphOutput | None
```

Do not merge SQL rows directly into a shared `messages` or generic `results` list. The merge node should combine `rag_result`, `sql_result`, and tool results deterministically.

## Should Subgraph State Be Separate From Main State?

Yes. The SQL subgraph should have its own internal state schema and a small adapter boundary.

Reason:

1. The parent graph state contains chat messages, RAG context, final answer state, citation validation, and audit metadata.
2. The SQL subgraph needs private state such as candidate SQL, schema context, safety validation results, retry count, execution errors, row count, and allowed table registry.
3. Keeping SQL internals private avoids leaking failed SQL attempts or schema details into the answer composer.
4. A wrapper node can convert parent state into `SQLSubgraphInput`, invoke the compiled SQL subgraph, and write back only `SQLSubgraphOutput`.

LangGraph can add a compiled subgraph directly as a node when parent and subgraph share state keys. For NexusOne, use a wrapper/adapter first because the SQL state is intentionally more constrained than the parent state.

Recommended shape:

```text
ParentGraphState
  -> sql_subgraph_adapter_node
      -> SQLSubgraphState
      -> compiled SQL subgraph
      -> SQLSubgraphOutput
  -> ParentGraphState.sql_result
```

## SQL Subgraph Internal State

Proposed state:

```python
from typing import Literal, TypedDict

class UserContext(TypedDict):
    user_id: str
    role: str
    department: str
    location: str
    groups: list[str]
    status: str

class AllowedSource(TypedDict):
    name: str
    kind: Literal["table", "view", "function"]
    business_domain: str
    description: str
    columns: list[str]
    required_filter: str | None
    max_rows: int

class SQLValidationResult(TypedDict):
    is_safe: bool
    reason: str | None
    used_tables: list[str]
    normalized_sql: str | None
    rewritten_sql: str | None

class SQLExecutionResult(TypedDict):
    columns: list[str]
    rows: list[dict]
    row_count: int
    elapsed_ms: int

class SQLSubgraphState(TypedDict):
    conversation_id: str
    turn_id: str
    user_id: str
    question: str
    requested_intent: str | None

    user_context: UserContext | None
    sql_intent: str | None
    allowed_sources: list[AllowedSource]
    schema_context: str

    candidate_sql: str | None
    checked_sql: str | None
    validation: SQLValidationResult | None

    execution_result: SQLExecutionResult | None
    attempts: int
    max_attempts: int

    sql_status: str
    refusal_reason: str | None
    error_message: str | None
    output: SQLSubgraphOutput | None
```

Keep model messages local to the subgraph if we need them for query generation. Do not return them to the parent graph.

## Node Graph

Recommended node sequence:

```text
START
  -> load_user_context
  -> classify_sql_intent
  -> select_allowed_sources
  -> build_schema_context
  -> draft_sql
  -> validate_sql_safety
  -> route_after_validation
      safe
        -> check_sql_with_llm
        -> validate_checked_sql
        -> execute_readonly_sql
        -> format_sql_evidence
        -> END
      invalid
        -> repair_sql
        -> validate_sql_safety
      unsafe
        -> refuse_sql_request
        -> END
      no_allowed_source
        -> no_allowed_source_response
        -> END
      needs_clarification
        -> clarification_response
        -> END
      execution_error
        -> repair_sql
        -> validate_sql_safety
```

Bounded retry:

```text
max_attempts = 2
```

If SQL generation or execution still fails after retries, return a safe error object to the parent graph. The parent can still answer with RAG if this was a mixed question.

## Node Responsibilities

### 1. `load_user_context`

Purpose:

- Load `users`, `user_groups`, role, department, location, and status.
- Fail closed if user is missing or inactive.

Inputs:

- `user_id`

Outputs:

- `user_context`
- `sql_status = "refused"` if the user is inactive or unknown

Database access:

```sql
SELECT u.user_id, u.role, u.department, u.location, u.status, array_agg(ug.group_name)
FROM users u
LEFT JOIN user_groups ug ON ug.user_id = u.user_id
WHERE u.user_id = :user_id
GROUP BY u.user_id;
```

### 2. `classify_sql_intent`

Purpose:

- Decide whether the SQL question is about public lookup, tickets, finance, HR, project status, documents metadata, or unsupported data.
- Detect ambiguity before SQL generation.

Implementation:

- Use OpenAI with structured output.
- Temperature `0`.
- The classifier should not generate SQL.

Output enum:

```text
public_lookup
ticket_status
finance_summary
finance_budget
finance_revenue_risk
vendor_aging
hr_headcount
hr_lifecycle
project_public
project_executive
document_metadata
unsupported
ambiguous
```

### 3. `select_allowed_sources`

Purpose:

- Convert user context and SQL intent into a strict source allowlist.
- This is deterministic code, not LLM-driven.

Initial source policy:

| Domain | Sources | Access |
| --- | --- | --- |
| Public lookup | `company_holidays`, `tool_directory`, `office_locations`, `project_status_public`, `employee_directory` limited columns | Active internal users |
| Tickets | `tickets`, `ticket_events` through `can_user_access_ticket` or future `accessible_tickets` view | Requester, assignee, queue owner role, manager of requester, CEO |
| Finance summary | `finance_summaries`, `department_budgets`, `vendor_payment_aging` | Finance, executive, CEO initially |
| Revenue risk | `revenue_risks` | Executive and CEO only |
| HR headcount | `headcount_plan`, `employee_lifecycle_slas`, `benefits_vendors` | HR, manager, executive, CEO where appropriate |
| Executive project status | `project_status_executive` | Executive and CEO |
| Document metadata | `user_accessible_documents` | All active users, filtered by `user_id` |

Fail closed:

- If no source is allowed, return `sql_status = "no_allowed_source"`.
- Do not ask the model to decide whether the user can access a table.

### 4. `build_schema_context`

Purpose:

- Provide the SQL drafting model with only allowed tables/views and safe column descriptions.
- Include sample rows only when samples are non-sensitive and permission-safe.

Implementation:

- Use a local `schema_registry.py`, not raw `information_schema` dumps.
- For sensitive tables, include columns and business meaning, but avoid sample sensitive values.
- For public lookup tables, sample rows are acceptable.

Output:

- `schema_context`

### 5. `draft_sql`

Purpose:

- Generate a PostgreSQL `SELECT` query for the question using only `schema_context`.

Implementation:

- Use OpenAI structured output:

```python
class DraftSQL(BaseModel):
    sql: str
    reasoning_summary: str
    expected_columns: list[str]
```

Prompt constraints:

- PostgreSQL dialect.
- Generate exactly one query.
- Use only allowed sources.
- Do not select unnecessary columns.
- Always include a limit unless the query is a single aggregate row.
- Use parameter placeholder for user filtering where needed, not interpolated user input.
- Never use DML or DDL.
- For tickets, include `can_user_access_ticket(:user_id, ticket_id)` unless using an access-safe view.
- For document metadata, query `user_accessible_documents` and filter `user_id = :user_id`.

### 6. `validate_sql_safety`

Purpose:

- Deterministically validate SQL before any execution or LLM query checker output is trusted.

Recommended library:

- `sqlglot` for parsing and table extraction.

Rules:

1. Allow only one statement.
2. Allow only `SELECT` or read-only `WITH ... SELECT`.
3. Reject `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `COPY`, `GRANT`, `REVOKE`, `CALL`, `DO`, `MERGE`.
4. Reject semicolon-separated multi-statements.
5. Reject comments that hide extra SQL.
6. Reject access to tables not in `allowed_sources`.
7. Reject system schemas such as `pg_catalog`, `information_schema`, and temp schemas.
8. Enforce `LIMIT <= configured_max_rows` unless the query is a single aggregate.
9. Enforce required permission predicates for sensitive sources.
10. Enforce parameter binding for `user_id`; never string interpolate user IDs.

If a query is valid but missing a limit, the validator may rewrite it by wrapping:

```sql
SELECT *
FROM (
  <candidate query>
) AS limited_query
LIMIT :max_rows
```

If the query is unsafe, refuse. If it is invalid but repairable, route to `repair_sql`.

### 7. `check_sql_with_llm`

Purpose:

- Catch common SQL mistakes after deterministic safety validation.

Borrowed from LangChain docs:

- The SQL tutorial uses a query checker before execution.

NexusOne change:

- The LLM checker is not a safety gate.
- Any SQL returned by this checker must run through `validate_checked_sql` before execution.

Common mistakes to check:

- Wrong joins.
- Missing group-by columns.
- Incorrect date comparisons.
- Wrong table aliases.
- Mistaken column names.
- Unnecessary `SELECT *`.
- Missing or incorrect permission predicate.

### 8. `validate_checked_sql`

Purpose:

- Re-run the deterministic validator on the checked SQL.

Reason:

- The LLM query checker may rewrite SQL.
- Any rewrite must satisfy the same allowlist, permission, and read-only rules.

### 9. `execute_readonly_sql`

Purpose:

- Execute only validated SQL.

Requirements:

1. Use a read-only database connection role if possible.
2. Use parameterized execution.
3. Set statement timeout.
4. Set transaction read-only.
5. Enforce row limit at the application layer after execution as a final guard.
6. Capture row count, columns, elapsed time, and query hash/id.

Example transaction behavior:

```sql
BEGIN READ ONLY;
SET LOCAL statement_timeout = '3000ms';
-- execute validated parameterized query
COMMIT;
```

Never expose raw database exception details to the final answer. Store safe error labels for debugging and audit.

### 10. `repair_sql`

Purpose:

- Repair syntax or semantic errors surfaced by validation or database execution.

Inputs to model:

- Original question.
- Allowed schema context.
- Previous SQL.
- Safe error summary.
- Attempt count.

Rules:

- No more than `max_attempts`.
- Repaired SQL must return to `validate_sql_safety`.

### 11. `format_sql_evidence`

Purpose:

- Convert rows into a safe structured result for the parent graph.

Output should include:

- `sql_status`
- `sql_answer_summary`
- `sql_rows`
- `sql_columns`
- `sql_sources`
- `sql_used_tables`
- `sql_query_id`
- `sql_denied_reason`
- `sql_error`

The SQL subgraph can produce a short summary, but the parent graph's final answer composer should still decide how to combine SQL with RAG evidence.

### 12. `refuse_sql_request`

Purpose:

- Return a safe refusal for unsupported, unsafe, or unauthorized structured-data requests.

Examples:

- User asks to update or delete records.
- User asks for executive-only revenue risk without access.
- User asks for raw audit logs.
- User asks for full employee personal details outside allowed columns.

## Tools To Create

Use LangChain tools only where tool abstraction helps. Keep core permission and validation logic as normal Python functions so it can be tested directly.

### LangChain Tools

These tools are safe to expose only inside the SQL subgraph:

#### `sql_list_allowed_sources`

Returns source names and descriptions from the already computed allowlist.

Input:

```python
{
  "intent": "finance_budget"
}
```

Output:

```python
{
  "sources": [
    {
      "name": "department_budgets",
      "kind": "table",
      "description": "Budget allocation, actual spend, forecast spend, variance, and risk level by department and period."
    }
  ]
}
```

#### `sql_get_schema_context`

Returns safe schema context for allowed sources only.

This can be a tool or a deterministic node. Prefer deterministic node first.

#### `sql_execute_readonly`

Executes a previously validated SQL query.

This should not be directly available to the parent graph or final answer agent.

Input:

```python
{
  "query_id": "validated query id",
  "parameters": {
    "user_id": "u001",
    "max_rows": 25
  }
}
```

Important: execution should accept only SQL that the validator has already stored or signed for the current turn. Do not let the model pass arbitrary SQL directly into this tool.

### Plain Python Services

These should be normal functions/classes:

- `load_user_context(user_id)`
- `select_allowed_sources(user_context, intent)`
- `validate_sql(query, allowed_sources, user_context, required_filters)`
- `extract_table_names(query)`
- `enforce_limit(query, max_rows)`
- `execute_validated_sql(validated_query, params)`
- `format_sql_result(execution_result, metadata)`
- `write_sql_audit_event(...)`

## Permission-Aware Database Layer

Current schema already includes:

- `can_user_access_document(p_user_id, p_doc_id)`
- `can_user_access_ticket(p_user_id, p_ticket_id)`
- `user_accessible_documents`

Recommended next SQL migration:

```text
data/postgres/init/005_permission_safe_views.sql
```

Add views/functions that make safe querying easier:

### `accessible_tickets`

Preferred implementation pattern:

- A SQL function taking `p_user_id`.
- Returning only ticket rows that pass `can_user_access_ticket`.

Example conceptual shape:

```sql
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
```

Avoid exposing raw ticket descriptions unless the question specifically requires them and access is allowed.

### `accessible_ticket_events`

Return ticket events only for tickets the user can access.

### Finance Safe Sources

Options:

1. Use deterministic source allowlist in Python for `finance_summaries`, `department_budgets`, `vendor_payment_aging`, and `revenue_risks`.
2. Later add SQL functions such as `accessible_finance_summaries(p_user_id)` and `accessible_revenue_risks(p_user_id)`.

For first implementation, deterministic Python allowlisting is acceptable, but the SQL validator must enforce that restricted finance tables are not available to normal employees.

### Employee Directory Safe Columns

Do not expose all user fields. The public employee directory path should only allow:

- name
- email
- department
- title
- location
- manager_id

Do not expose internal role permissions, group memberships, or inactive users through generic lookup.

## SQL Source Registry

Create `schema_registry.py` with a declarative registry.

Example:

```python
SQL_SOURCE_REGISTRY = {
    "company_holidays": {
        "domain": "public_lookup",
        "access": {"roles": "all_active"},
        "columns": {
            "region": "Country or regional office grouping.",
            "holiday_name": "Holiday display name.",
            "date": "Holiday date.",
            "type": "Holiday type.",
            "notes": "Short note."
        },
        "max_rows": 50,
    },
    "department_budgets": {
        "domain": "finance_budget",
        "access": {"roles": ["finance", "executive", "ceo"]},
        "columns": {
            "period": "Budget period.",
            "department": "Department name.",
            "allocated_budget": "Approved budget.",
            "actual_spend": "Spend to date.",
            "forecast_spend": "Forecast final spend.",
            "variance": "Forecast minus allocated budget.",
            "risk_level": "Budget risk label."
        },
        "max_rows": 25,
    },
}
```

The LLM should only see schema entries selected by this registry.

## Prompt Plan

### SQL Intent Classifier Prompt

Purpose:

- Classify the user question into one SQL domain.
- Identify if the question needs clarification.
- Identify if SQL is unsupported.

Return structured JSON:

```json
{
  "intent": "finance_budget",
  "confidence": 0.92,
  "needs_clarification": false,
  "clarifying_question": null,
  "reason": "The question asks for department budget utilization."
}
```

### SQL Draft Prompt

Key instructions:

```text
You generate PostgreSQL SELECT queries for NexusOne's structured data subgraph.
Use only the provided schema context.
Return exactly one SQL query.
Do not include explanations in the SQL field.
Do not use DML, DDL, stored procedures, system catalogs, temp tables, or multiple statements.
Use named parameters for user-specific filters, especially :user_id.
Use only necessary columns.
Use LIMIT unless the query returns a single aggregate row.
```

### Query Checker Prompt

Purpose:

- Review SQL for correctness, not authorization.
- Return corrected SQL only.

Important:

- The deterministic validator still runs after this prompt.

## Main Graph Integration

The parent graph's intent router should handle mixed questions by fanning out to both RAG and SQL.

For a SQL-only question:

```text
START -> load_parent_context -> intent_router -> sql_subgraph_adapter -> merge_evidence -> compose_answer
```

For a mixed question:

```text
intent_router
  -> rag_subgraph
  -> sql_subgraph_adapter
both -> merge_evidence -> compose_answer
```

The SQL subgraph should not compose the final user-facing answer alone unless the parent graph asked for SQL-only output. Even then, the parent should run the final guardrail/validator.

## Audit And Observability

Each SQL subgraph run should log:

- conversation_id
- turn_id
- user_id
- sql_intent
- allowed sources
- used tables
- query hash or query id
- row count
- status
- denied reason if any
- execution latency
- model name used for SQL generation
- validation failure reason if any

Do not log raw secrets. For demo data, logging query text is acceptable during development, but prefer query hash plus sanitized SQL in production-shaped code.

## Security Rules

Non-negotiable rules:

1. The parent assistant never receives an unrestricted SQL execution tool.
2. SQL execution never runs before deterministic validation.
3. The LLM never decides permissions.
4. Generated SQL cannot access non-allowlisted tables.
5. Ticket queries must use `can_user_access_ticket` or an access-safe ticket function/view.
6. Document metadata queries must use `user_accessible_documents` filtered by `user_id`.
7. Normal employees cannot access finance, executive, HR-sensitive, or CEO-only structured data.
8. Unsafe SQL is refused, not repaired, when it attempts DML, DDL, system schema access, or multi-statement execution.
9. Query repair is bounded.
10. Result size is limited.

## Implementation Phases

### Phase 1: Database Safety Layer

Create:

```text
data/postgres/init/005_permission_safe_views.sql
```

Add:

- `accessible_tickets(p_user_id)`
- `accessible_ticket_events(p_user_id)`
- optional `active_employee_directory_public`

Validation:

- Employee can only see own/assigned/allowed ticket rows.
- Department queue owners can see their queue.
- CEO can see all tickets.
- Public lookup tables still work for all active users.

### Phase 2: Core SQL Validator

Create:

```text
app/agents/sql_subgraph/sql_validator.py
```

Implement:

- single-statement validation
- read-only validation
- allowlisted table extraction
- blocked keyword detection
- required permission predicate checks
- limit enforcement

Tests:

- rejects `DELETE`
- rejects `DROP`
- rejects multi-statement SQL
- rejects non-allowlisted tables
- rejects raw `tickets` query without permission predicate
- accepts safe aggregate query on `department_budgets` for finance user
- accepts public holiday lookup for employee

### Phase 3: Source Registry And Scope Selection

Create:

```text
app/agents/sql_subgraph/schema_registry.py
app/agents/sql_subgraph/permissions.py
```

Implement deterministic role-to-source policy.

Tests:

- employee gets public lookup sources only, plus accessible ticket function.
- finance gets finance summaries, budgets, vendor aging.
- executive gets executive project status and revenue risk.
- CEO gets all structured sources.

### Phase 4: Subgraph State And Nodes

Create:

```text
app/agents/sql_subgraph/state.py
app/agents/sql_subgraph/nodes.py
app/agents/sql_subgraph/graph.py
```

Implement:

- `load_user_context`
- `classify_sql_intent`
- `select_allowed_sources`
- `build_schema_context`
- `draft_sql`
- `validate_sql_safety`
- `check_sql_with_llm`
- `validate_checked_sql`
- `execute_readonly_sql`
- `repair_sql`
- `format_sql_evidence`
- refusal and clarification nodes

### Phase 5: OpenAI And LangChain Integration

Add model factory:

```text
app/gateway/providers/openai.py
```

or reuse a project-wide gateway if it already exists when implementation starts.

Requirements:

- environment-based model name
- temperature `0`
- structured output for classifier and SQL drafter
- no API key hard-coded

### Phase 6: Parent Adapter

Create:

```text
app/agents/nodes/sql_subgraph_adapter.py
```

Responsibilities:

- read `user_id`, `question`, `sql_question`, `conversation_id`, `turn_id`
- invoke compiled SQL subgraph
- write `sql_result` into parent state
- never expose internal SQL state to the parent answer composer

### Phase 7: Integration Tests

Add tests for:

- "What holidays apply in Pakistan?"
- "Show department budget utilization."
- "Which vendors are overdue?"
- "What is my ticket status?"
- "Show all finance risks" as employee should refuse/no allowed source.
- "Compare Q4 hiring plan with budget risks" as finance/executive should route SQL and later merge with RAG.
- "Compare Q4 hiring plan with budget risks" as employee should return only allowed structured rows and not expose restricted finance/executive rows.

## Acceptance Criteria

The SQL subgraph is ready when:

1. It can answer public lookup questions from PostgreSQL.
2. It can answer finance questions only for authorized users.
3. It can answer ticket questions only when `can_user_access_ticket` allows access.
4. It refuses unsafe SQL requests.
5. It refuses or safely reports no access for unauthorized structured data.
6. It never executes multi-statement, DML, DDL, or non-allowlisted SQL.
7. It enforces row limits.
8. It returns structured rows and source metadata to the parent graph.
9. It logs status, used tables, row count, and denial/error reasons.
10. It can be called by the parent graph as a clean subgraph node/adapter.

## First Concrete Build Step

Start with the deterministic pieces before the OpenAI nodes:

1. Add permission-safe SQL functions/views in `005_permission_safe_views.sql`.
2. Add `schema_registry.py`.
3. Add `permissions.py`.
4. Add `sql_validator.py`.
5. Add unit tests for validator and source selection.

After those pass, add OpenAI-powered intent classification and SQL drafting nodes.
