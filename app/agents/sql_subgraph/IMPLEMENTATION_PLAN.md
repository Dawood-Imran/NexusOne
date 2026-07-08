# SQL Subgraph Implementation Plan

## Purpose

The SQL subgraph is the independent structured-data connector for NexusOne Copilot. It answers exact data questions from PostgreSQL while keeping permissions deterministic and auditable.

## Design

The subgraph is intentionally separate from the future main assistant graph. It can run independently from tests, the terminal chatbot, or the web chat service.

Node flow:

1. `load_user_context`
2. `classify_sql_intent`
3. `select_allowed_sources`
4. `build_schema_context`
5. `draft_sql`
6. `validate_sql_safety`
7. `execute_or_package`
8. `check_answer_grounding`

Repair loop nodes:

- `record_validation_feedback`
- `record_execution_feedback`
- `record_answer_feedback`
- `repair_sql`
- `finalize_repair_failure`

## Safety Rules

- Source selection is deterministic code.
- The planner only sees allowlisted schema context.
- SQL must be read-only, single statement, and source allowlisted.
- User-scoped functions must include `:user_id`.
- Hidden raw identifiers are blocked from selected output columns.
- Final presentation sanitizes rows again before display.
- Repair attempts are bounded.

## Current Status

Implemented and covered by unit tests under `tests/unit/agents/sql_subgraph/`.
