# SQL Repair Loop Implementation Plan

## Problem

An LLM planner can draft SQL that is syntactically plausible but unsafe or not shaped to answer the user question. Examples include selecting raw user IDs, using a broad ticket query for an assignee question, or omitting required `:user_id` scoping.

## Solution

The subgraph validates every SQL draft before execution. If validation, execution, or answer grounding fails, the graph records safe feedback and loops through `repair_sql`.

## Loop

```text
draft_sql
  -> validate_sql_safety
    -> execute_or_package
      -> check_answer_grounding
        -> END

validation/execution/grounding failure
  -> record_*_feedback
  -> repair_sql
  -> validate_sql_safety
```

## Guardrails

- Maximum repair attempts: 2.
- Feedback never includes unrestricted schema or hidden row values.
- `user_id` is always overwritten with the trusted current user.
- Ticket assignment questions must use `accessible_ticket_assignments(:user_id)`.
- If repair fails, the graph returns a safe refusal/error instead of executing unsafe SQL.

## Verification

Current unit tests verify:

- Unsafe hidden ticket columns are repaired.
- Planner cannot override trusted `user_id`.
- Assignment questions route to the safe assignment function.
- Terminal escape artifacts are removed before routing.
- Final presentation does not print raw internal user IDs.
