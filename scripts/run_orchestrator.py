#!/usr/bin/env python
"""Run the NexusOne main orchestrator graph from the terminal."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agents.orchestrator import NexusOneOrchestrator
from app.agents.orchestrator.answer_composer import DeterministicAnswerComposer
from app.agents.sql_subgraph.db import SQLAlchemyExecutor


DEFAULT_DATABASE_URL = "postgresql+psycopg2://nexusone:nexusone_dev_password@localhost:5492/nexusone"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the NexusOne Phase 3 orchestrator graph.")
    parser.add_argument("message", help="User message to send through the graph.")
    parser.add_argument("--user-id", default="u001", help="NexusOne demo user id. Defaults to u001.")
    parser.add_argument("--conversation-id", default="cli")
    parser.add_argument("--turn-id", default="cli-1")
    parser.add_argument("--dotenv", default=".env", help="Env file to load before running. Defaults to .env.")
    parser.add_argument("--execute-sql", action="store_true", help="Execute validated SQL against local Postgres.")
    parser.add_argument("--database-url", default=None, help="SQLAlchemy database URL.")
    parser.add_argument("--trace", action="store_true", help="Print graph trace and SQL subgraph trace.")
    parser.add_argument("--approve-ticket", action="store_true", help="After a ticket preview, send an explicit approval turn.")
    parser.add_argument("--deny-ticket", action="store_true", help="After a ticket preview, send an explicit denial turn.")
    parser.add_argument(
        "--deterministic-composer",
        action="store_true",
        help="Use the local deterministic final-answer composer instead of OpenAI.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    load_dotenv(ROOT / args.dotenv)

    executor = None
    if args.execute_sql:
        database_url = args.database_url or os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL
        executor = SQLAlchemyExecutor(database_url=database_url)

    answer_composer = DeterministicAnswerComposer() if args.deterministic_composer else None
    orchestrator = NexusOneOrchestrator(sql_executor=executor, answer_composer=answer_composer)
    request_payload = {
        "conversation_id": args.conversation_id,
        "turn_id": args.turn_id,
        "user_id": args.user_id,
        "message": args.message,
        "include_trace": args.trace,
        "execute_sql": args.execute_sql,
    }
    response = orchestrator.invoke(request_payload)
    if response.get("status") == "needs_approval" and (args.approve_ticket or args.deny_ticket):
        request_payload = {
            **request_payload,
            "turn_id": f"{args.turn_id}-approval",
            "message": "Approve ticket" if args.approve_ticket else "Cancel ticket",
            "ticket_workflow": "approve" if args.approve_ticket else "deny",
        }
        response = orchestrator.invoke(request_payload)
    _print_response(dict(response), include_trace=args.trace)
    return 0


def _print_response(response: dict[str, Any], include_trace: bool) -> None:
    trace = response.pop("trace", None)
    subgraph_trace = response.pop("subgraph_trace", None)
    print(json.dumps(response, indent=2, default=str))
    if include_trace and trace is not None:
        print("\nGraph trace")
        print("-" * 80)
        for index, step in enumerate(trace, start=1):
            print(f"{index}. {step.get('node')}")
            for key, value in dict(step.get("details", {})).items():
                print(f"   {key}: {value}")
    if include_trace and subgraph_trace is not None:
        print("\nSQL subgraph trace")
        print("-" * 80)
        for index, step in enumerate(subgraph_trace, start=1):
            print(f"{index}. {step.get('node')}")
            details = dict(step.get("details", {}))
            print(f"   status: {details.get('status')}")
            if details.get("intent"):
                print(f"   intent: {details.get('intent')}")
            if details.get("allowed_sources"):
                print(f"   allowed_sources: {details.get('allowed_sources')}")


if __name__ == "__main__":
    raise SystemExit(main())
