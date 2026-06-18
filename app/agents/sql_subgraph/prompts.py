"""Prompt templates for the later OpenAI-backed SQL planner."""

SQL_INTENT_CLASSIFIER_PROMPT = """\
Classify the user's structured-data request for the NexusOne SQL subgraph.
Return only structured output matching the configured schema.
Do not generate SQL.
"""

SQL_DRAFT_PROMPT = """\
You generate PostgreSQL SELECT queries for NexusOne's structured-data subgraph.
Use only the provided schema context.
Return exactly one SQL query.
Do not use DML, DDL, stored procedures, system catalogs, temp tables, or multiple statements.
Use named parameters for user-specific filters, especially :user_id.
Use only necessary columns.
Use LIMIT unless the query returns a single aggregate row.
"""

SQL_CHECKER_PROMPT = """\
Review the PostgreSQL query for correctness.
Check joins, aliases, column names, grouping, date filters, and required user filters.
Return the corrected SQL only.
The deterministic SQL validator will run after this check.
"""

