"""State objects for the independent SQL subgraph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Protocol


SQLIntent = Literal[
    "public_lookup",
    "ticket_status",
    "finance_summary",
    "finance_budget",
    "finance_revenue_risk",
    "vendor_aging",
    "hr_headcount",
    "hr_lifecycle",
    "project_public",
    "project_executive",
    "document_metadata",
    "unsupported",
    "ambiguous",
]

SQLStatus = Literal[
    "answered",
    "validated",
    "no_allowed_source",
    "needs_clarification",
    "refused",
    "error",
]

SourceKind = Literal["table", "view", "function"]


@dataclass(frozen=True)
class UserContext:
    user_id: str
    role: str
    department: str
    location: str
    groups: tuple[str, ...] = ()
    status: str = "active"


@dataclass(frozen=True)
class SourceColumn:
    name: str
    description: str


@dataclass(frozen=True)
class SourceDefinition:
    name: str
    kind: SourceKind
    domain: str
    description: str
    columns: tuple[SourceColumn, ...]
    access_roles: tuple[str, ...] | Literal["all_active"]
    max_rows: int = 25
    requires_user_id: bool = False
    sensitive: bool = False

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)


@dataclass(frozen=True)
class SQLSubgraphInput:
    conversation_id: str
    turn_id: str
    user_id: str
    question: str
    sql_question: str | None = None
    requested_intent: str | None = None
    user_context: UserContext | None = None
    execute: bool = True


@dataclass(frozen=True)
class SQLValidationResult:
    is_safe: bool
    reason: str | None = None
    used_sources: tuple[str, ...] = ()
    normalized_sql: str | None = None
    rewritten_sql: str | None = None
    feedback_for_repair: str | None = None

    @property
    def sql_to_execute(self) -> str | None:
        return self.rewritten_sql or self.normalized_sql


@dataclass(frozen=True)
class SQLExecutionResult:
    columns: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    row_count: int
    elapsed_ms: int = 0


@dataclass(frozen=True)
class SQLSubgraphOutput:
    sql_status: SQLStatus
    sql_answer_summary: str
    sql_rows: tuple[Mapping[str, Any], ...] = ()
    sql_columns: tuple[str, ...] = ()
    sql_sources: tuple[Mapping[str, Any], ...] = ()
    sql_used_tables: tuple[str, ...] = ()
    sql_query: str | None = None
    sql_query_id: str | None = None
    sql_parameters: Mapping[str, Any] = field(default_factory=dict)
    sql_denied_reason: str | None = None
    sql_error: str | None = None


@dataclass(frozen=True)
class SQLNodeTrace:
    node_name: str
    details: Mapping[str, Any]


@dataclass(frozen=True)
class SQLSubgraphRun:
    output: SQLSubgraphOutput
    traces: tuple[SQLNodeTrace, ...]


@dataclass
class SQLSubgraphState:
    conversation_id: str
    turn_id: str
    user_id: str
    question: str
    requested_intent: str | None = None
    execute: bool = True

    user_context: UserContext | None = None
    sql_intent: SQLIntent | None = None
    allowed_sources: tuple[SourceDefinition, ...] = ()
    schema_context: str = ""

    candidate_sql: str | None = None
    sql_parameters: dict[str, Any] = field(default_factory=dict)
    validation: SQLValidationResult | None = None
    execution_result: SQLExecutionResult | None = None

    repair_attempts: int = 0
    max_repair_attempts: int = 2
    planner_error: str | None = None
    validation_feedback: str | None = None
    execution_feedback: str | None = None
    answer_feedback: str | None = None
    repair_history: list[str] = field(default_factory=list)
    final_answer_grounded: bool = False

    sql_status: SQLStatus = "error"
    refusal_reason: str | None = None
    error_message: str | None = None
    output: SQLSubgraphOutput | None = None


class SQLExecutor(Protocol):
    """Small executor interface so the subgraph can run outside the parent app."""

    def fetch_one(self, query: str, parameters: Mapping[str, Any]) -> Mapping[str, Any] | None:
        """Fetch one row from the database."""

    def fetch_all(
        self,
        query: str,
        parameters: Mapping[str, Any],
        max_rows: int,
    ) -> SQLExecutionResult:
        """Fetch rows from the database."""


class SQLPlanner(Protocol):
    """Planner interface for LLM-backed SQL classification and drafting."""

    def classify_intent(
        self,
        question: str,
        requested_intent: str | None,
        known_intents: set[str],
    ) -> SQLIntent:
        """Classify a question into one SQL intent."""

    def draft_sql(
        self,
        question: str,
        intent: SQLIntent,
        schema_context: str,
        allowed_sources: tuple[SourceDefinition, ...],
        user_id: str,
    ) -> tuple[str, Mapping[str, Any]]:
        """Draft SQL and named parameters for the allowed schema context."""

    def repair_sql(
        self,
        question: str,
        intent: SQLIntent,
        schema_context: str,
        allowed_sources: tuple[SourceDefinition, ...],
        previous_sql: str,
        previous_parameters: Mapping[str, Any],
        feedback: str,
        user_id: str,
    ) -> tuple[str, Mapping[str, Any]]:
        """Repair a failed SQL draft using safe feedback."""
