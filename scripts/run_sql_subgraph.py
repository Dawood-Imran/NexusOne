#!/usr/bin/env python
"""Run the NexusOne SQL subgraph against local Postgres."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine

from app.agents.sql_subgraph import SQLSubgraph
from app.agents.sql_subgraph.db import SQLAlchemyExecutor


DEFAULT_DATABASE_URL = "postgresql+psycopg2://nexusone:nexusone_dev_password@localhost:5492/nexusone"
HELPERS_SQL_PATH = ROOT / "data" / "postgres" / "init" / "005_permission_safe_views.sql"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


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
    parser = argparse.ArgumentParser(description="Run the standalone NexusOne SQL subgraph.")
    parser.add_argument("question", help="Question to answer from structured Postgres data.")
    parser.add_argument("--user-id", default="u001", help="NexusOne user id. Defaults to u001.")
    parser.add_argument("--intent", default=None, help="Optional SQL intent override.")
    parser.add_argument("--role", default=None, help="Optional role for no-DB validation runs.")
    parser.add_argument("--department", default="engineering", help="Department when --role is used.")
    parser.add_argument("--location", default="Pakistan", help="Location when --role is used.")
    parser.add_argument("--database-url", default=None, help="SQLAlchemy database URL.")
    parser.add_argument("--dotenv", default=".env", help="Env file to load before running. Defaults to .env.")
    parser.add_argument("--no-openai", action="store_true", help="Use deterministic planner instead of LangChain OpenAI.")
    parser.add_argument("--no-execute", action="store_true", help="Validate SQL without executing it.")
    parser.add_argument(
        "--apply-db-helpers",
        action="store_true",
        help="Apply data/postgres/init/005_permission_safe_views.sql before running.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    load_dotenv(ROOT / args.dotenv)

    database_url = args.database_url or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
    if args.apply_db_helpers:
        apply_db_helpers(database_url)

    needs_database = not args.no_execute or args.role is None
    executor = SQLAlchemyExecutor(database_url=database_url) if needs_database else None
    planner = None
    if not args.no_openai:
        from app.agents.sql_subgraph.planner import LangChainOpenAISQLPlanner

        planner = LangChainOpenAISQLPlanner.from_env()

    payload: dict[str, Any] = {
        "conversation_id": "cli",
        "turn_id": "cli-1",
        "user_id": args.user_id,
        "question": args.question,
        "requested_intent": args.intent,
        "execute": not args.no_execute,
    }
    if args.role is not None:
        payload["user_context"] = {
            "user_id": args.user_id,
            "role": args.role,
            "department": args.department,
            "location": args.location,
        }

    output = SQLSubgraph(executor=executor, planner=planner).invoke(payload)

    print(json.dumps(asdict(output), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
