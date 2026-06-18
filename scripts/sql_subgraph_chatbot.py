#!/usr/bin/env python
"""Interactive terminal chatbot for the NexusOne SQL subgraph."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.sql_subgraph import SQLSubgraph, SQLSubgraphOutput, SQLSubgraphRun
from app.agents.sql_subgraph.db import SQLAlchemyExecutor
from app.agents.sql_subgraph.presentation import format_safe_terminal_answer, safe_summary_payload


DEFAULT_DATABASE_URL = "postgresql+psycopg2://nexusone:nexusone_dev_password@localhost:5492/nexusone"
HELPERS_SQL_PATH = ROOT / "data" / "postgres" / "init" / "005_permission_safe_views.sql"

NODE_DESCRIPTIONS = {
    "load_user_context": "Loads the user role, department, location, status, and groups from Postgres unless user context was supplied.",
    "classify_sql_intent": "Finds the structured-data intent. Uses OpenAI when enabled; otherwise uses deterministic keyword rules.",
    "select_allowed_sources": "Chooses allowlisted tables/views/functions for the user role and intent. Permissions are deterministic code.",
    "build_schema_context": "Builds a compact schema prompt from allowed sources only. The model never sees unrestricted DB schema.",
    "draft_sql": "Drafts a PostgreSQL SELECT query. Uses OpenAI when enabled; otherwise uses deterministic SQL templates.",
    "validate_sql_safety": "Validates the SQL before execution: SELECT-only, one statement, allowed sources, required user filters, and row limits.",
    "execute_or_package": "Executes validated SQL against Postgres, or packages the validated SQL when execution is disabled.",
}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def apply_db_helpers(database_url: str) -> None:
    sql = HELPERS_SQL_PATH.read_text(encoding="utf-8")
    engine = create_engine(database_url)
    raw_connection = engine.raw_connection()
    try:
        raw_connection.autocommit = True
        cursor = raw_connection.cursor()
        try:
            cursor.execute(sql)
        finally:
            cursor.close()
    finally:
        raw_connection.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive SQL-subgraph terminal chatbot.")
    parser.add_argument("--user-id", default="u001", help="NexusOne user id. Defaults to u001.")
    parser.add_argument("--database-url", default=None, help="SQLAlchemy database URL.")
    parser.add_argument("--dotenv", default=".env", help="Env file to load. Defaults to .env.")
    parser.add_argument("--role", default=None, help="Optional role for offline validation runs.")
    parser.add_argument("--department", default="engineering", help="Department when --role is used.")
    parser.add_argument("--location", default="Pakistan", help="Location when --role is used.")
    parser.add_argument("--no-openai", action="store_true", help="Use deterministic intent and SQL drafting.")
    parser.add_argument("--no-execute", action="store_true", help="Validate SQL without executing it.")
    parser.add_argument("--show-nodes", action="store_true", help="Show sanitized node-by-node trace output.")
    parser.add_argument("--hide-nodes", action="store_true", help="Deprecated compatibility flag; node trace is hidden by default.")
    parser.add_argument("--skip-db-helpers", action="store_true", help="Do not apply safe DB helper functions on startup.")
    return parser


def make_planner(use_openai: bool):
    if not use_openai:
        return None
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is missing. Add it to .env or export it, or run with --no-openai.")

    from app.agents.sql_subgraph.planner import LangChainOpenAISQLPlanner

    return LangChainOpenAISQLPlanner.from_env()


def summarize_with_openai(question: str, output: SQLSubgraphOutput, planner: Any) -> str | None:
    if planner is None or output.sql_status not in {"answered", "validated"}:
        return None
    model = getattr(planner, "model", None)
    if model is None:
        return None

    payload = safe_summary_payload(question, output)
    response = model.invoke(
        [
            (
                "system",
                "Answer the user using only the SQL subgraph result provided. "
                "If rows are empty, say that no matching structured rows were found. "
                "Do not invent facts or mention inaccessible data. "
                "Do not mention raw user IDs, assignee IDs, requester IDs, owner IDs, SQL, parameters, or internal paths. "
                "Answer only the question asked, using the smallest useful set of fields.",
            ),
            ("human", json.dumps(payload, default=str)),
        ]
    )
    return str(response.content)


def print_trace(run: SQLSubgraphRun) -> None:
    print("\nNode trace")
    print("-" * 80)
    for index, trace in enumerate(run.traces, start=1):
        print(f"{index}. {trace.node_name}")
        print(f"   What it does: {NODE_DESCRIPTIONS.get(trace.node_name, 'No description available.')}")
        details = dict(trace.details)
        for key in ("status", "intent", "allowed_sources", "schema_context_chars"):
            if details.get(key) not in (None, [], {}, ""):
                print(f"   {key}: {details[key]}")
        parameters = details.get("parameters")
        if parameters:
            print(f"   parameter_keys: {sorted(parameters.keys())}")
        user = details.get("user")
        if user:
            print(
                "   user: "
                f"role={user['role']} department={user['department']} "
                f"location={user['location']} status={user['status']}"
            )
        validation = details.get("validation")
        if validation:
            print(f"   validation: safe={validation['is_safe']} reason={validation['reason']}")
        execution = details.get("execution")
        if execution:
            print(f"   execution: rows={execution['row_count']} elapsed_ms={execution['elapsed_ms']}")
        output = details.get("output")
        if output:
            print(f"   output: status={output['status']} rows={output['row_count']} summary={output['summary']}")
        note = details.get("internal_note")
        if note:
            print(f"   internal_note: {note}")
        print()


def print_rows(output: SQLSubgraphOutput) -> None:
    print(format_safe_terminal_answer(output))


def print_intro(user_id: str, use_openai: bool, show_nodes: bool, execute: bool) -> None:
    mode = "OpenAI + deterministic validator" if use_openai else "deterministic keyword/templates only"
    print("NexusOne SQL Subgraph Chatbot")
    print("=" * 80)
    print("User: configured")
    print(f"Mode: {mode}")
    print(f"Execution: {'Postgres query execution enabled' if execute else 'SQL validation only'}")
    print(f"Node trace: {'shown' if show_nodes else 'hidden'}")
    print("Commands: /exit, /quit, /user <id>, /trace on, /trace off")
    print()


def main() -> int:
    args = build_parser().parse_args()
    load_dotenv(ROOT / args.dotenv)

    database_url = args.database_url or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
    if not args.skip_db_helpers and not args.no_execute:
        apply_db_helpers(database_url)

    planner = make_planner(use_openai=not args.no_openai)
    executor = None if args.no_execute and args.role is not None else SQLAlchemyExecutor(database_url=database_url)
    graph = SQLSubgraph(executor=executor, planner=planner)

    current_user_id = args.user_id
    show_nodes = args.show_nodes and not args.hide_nodes
    print_intro(current_user_id, planner is not None, show_nodes, not args.no_execute)

    while True:
        try:
            question = input("user> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        if not question:
            continue
        if question in {"/exit", "/quit"}:
            return 0
        if question.startswith("/user "):
            current_user_id = question.split(maxsplit=1)[1].strip()
            print("Switched active user.")
            continue
        if question == "/trace on":
            show_nodes = True
            print("Node trace enabled.")
            continue
        if question == "/trace off":
            show_nodes = False
            print("Node trace disabled.")
            continue

        payload: dict[str, Any] = {
            "conversation_id": "terminal-chat",
            "turn_id": "terminal-turn",
            "user_id": current_user_id,
            "question": question,
            "execute": not args.no_execute,
        }
        if args.role is not None:
            payload["user_context"] = {
                "user_id": current_user_id,
                "role": args.role,
                "department": args.department,
                "location": args.location,
            }

        run = graph.invoke_with_trace(payload)
        if show_nodes:
            print_trace(run)

        openai_answer = summarize_with_openai(question, run.output, planner)
        print("Answer")
        print("-" * 80)
        if openai_answer:
            print(openai_answer)
        else:
            print_rows(run.output)
        print()


if __name__ == "__main__":
    raise SystemExit(main())
