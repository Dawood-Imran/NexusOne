"""Optional database executor for running the SQL subgraph independently."""

from __future__ import annotations

import time
from typing import Any, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.agents.sql_subgraph.state import SQLExecutionResult


class SQLAlchemyExecutor:
    """Small SQLAlchemy-backed executor matching the SQLExecutor protocol."""

    def __init__(self, database_url: str | None = None, engine: Engine | None = None) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required.")
        self.engine = engine or create_engine(database_url)  # type: ignore[arg-type]

    def fetch_one(self, query: str, parameters: Mapping[str, Any]) -> Mapping[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(query), dict(parameters)).mappings().first()
        return dict(row) if row is not None else None

    def fetch_all(
        self,
        query: str,
        parameters: Mapping[str, Any],
        max_rows: int,
    ) -> SQLExecutionResult:
        started = time.perf_counter()
        with self.engine.connect() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '3000ms'"))
            result = connection.execute(text(query), dict(parameters)).mappings().fetchmany(max_rows)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        rows = tuple(dict(row) for row in result)
        columns = tuple(rows[0].keys()) if rows else ()
        return SQLExecutionResult(columns=columns, rows=rows, row_count=len(rows), elapsed_ms=elapsed_ms)

