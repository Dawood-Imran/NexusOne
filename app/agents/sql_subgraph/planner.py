"""LangChain OpenAI planner for the SQL subgraph."""

from __future__ import annotations

import os
from typing import Any, Literal, Mapping

from pydantic import BaseModel, Field

from app.agents.sql_subgraph.state import SQLIntent, SourceDefinition


class SQLIntentPlan(BaseModel):
    intent: Literal[
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
    ] = Field(description="The best SQL intent for the user question.")
    confidence: float = Field(description="Classification confidence between 0 and 1.", ge=0, le=1)
    reason: str = Field(description="Short reason for the classification.")


class SQLDraftPlan(BaseModel):
    sql: str = Field(description="One PostgreSQL SELECT query using only the allowed schema context.")
    parameters: dict[str, str | int | float | bool] = Field(
        default_factory=dict,
        description="Named SQL parameters. Always include user_id when :user_id is used.",
    )
    expected_columns: list[str] = Field(default_factory=list, description="Expected output columns.")
    reason: str = Field(description="Short reason for the SQL shape.")


class LangChainOpenAISQLPlanner:
    """OpenAI planner implemented through LangChain's ChatOpenAI integration."""

    provider_name = "openai"

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float | None = None,
    ) -> None:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover - depends on optional env package.
            raise RuntimeError(
                "langchain-openai is required for OpenAI planning. "
                'Install with: pip install -U "langchain[openai]"'
            ) from exc

        self.model_name = model_name or os.getenv("OPENAI_SQL_MODEL", "gpt-4.1-mini")
        self.temperature = temperature if temperature is not None else float(os.getenv("OPENAI_SQL_TEMPERATURE", "0"))
        self.model = ChatOpenAI(model=self.model_name, temperature=self.temperature)

    @classmethod
    def from_env(cls) -> "LangChainOpenAISQLPlanner":
        return cls()

    def safe_metadata(self) -> dict[str, object]:
        return {
            "provider": self.provider_name,
            "model": self.model_name,
            "temperature": self.temperature,
        }

    def classify_intent(
        self,
        question: str,
        requested_intent: str | None,
        known_intents: set[str],
    ) -> SQLIntent:
        if requested_intent in known_intents:
            return requested_intent  # type: ignore[return-value]

        structured_model = self.model.with_structured_output(SQLIntentPlan, method="function_calling")
        response = structured_model.invoke(
            [
                (
                    "system",
                    "Classify the user's request for the NexusOne SQL subgraph. "
                    "Return one intent only. If the question cannot be answered from structured "
                    "PostgreSQL data, return unsupported. If it is unclear, return ambiguous. "
                    f"Known intents: {', '.join(sorted(known_intents))}.",
                ),
                ("human", question),
            ]
        )
        return response.intent

    def draft_sql(
        self,
        question: str,
        intent: SQLIntent,
        schema_context: str,
        allowed_sources: tuple[SourceDefinition, ...],
        user_id: str,
    ) -> tuple[str, Mapping[str, Any]]:
        return self._draft_or_repair_sql(question, intent, schema_context, allowed_sources, user_id)

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
        repair_context = (
            f"Previous SQL failed validation/grounding.\n"
            f"Safe feedback: {feedback}\n"
            "Repair the query. Do not repeat hidden columns or non-allowlisted sources."
        )
        return self._draft_or_repair_sql(question, intent, f"{schema_context}\n\n{repair_context}", allowed_sources, user_id)

    def _draft_or_repair_sql(
        self,
        question: str,
        intent: SQLIntent,
        schema_context: str,
        allowed_sources: tuple[SourceDefinition, ...],
        user_id: str,
    ) -> tuple[str, Mapping[str, Any]]:
        source_names = ", ".join(source.name for source in allowed_sources)
        structured_model = self.model.with_structured_output(SQLDraftPlan, method="function_calling")
        response = structured_model.invoke(
            [
                (
                    "system",
                    "You generate PostgreSQL SELECT queries for NexusOne's SQL subgraph.\n"
                    "Use only the allowed schema context and allowed sources.\n"
                    "Return exactly one SQL query.\n"
                    "Never use DML, DDL, stored procedures, system schemas, temp tables, comments, or multiple statements.\n"
                    "Use named parameters with colon syntax, for example :user_id.\n"
                    "Always include user_id in parameters when :user_id appears in the SQL.\n"
                    "Do not select raw user-id fields such as requester_id, assigned_to, actor_user_id, manager_id, owner, or user_id.\n"
                    "For assignment display questions, use accessible_ticket_assignments(:user_id) and safe display fields.\n"
                    "For ticket status, use accessible_tickets(:user_id) or accessible_ticket_assignments(:user_id).\n"
                    "For document metadata, use user_accessible_documents with WHERE user_id = :user_id.\n"
                    "Use LIMIT unless the query returns a single aggregate row.\n"
                    f"Intent: {intent}\n"
                    f"Allowed sources: {source_names}\n\n"
                    f"Schema context:\n{schema_context}",
                ),
                ("human", question),
            ]
        )
        parameters: dict[str, Any] = dict(response.parameters)
        if ":user_id" in response.sql and "user_id" not in parameters:
            parameters["user_id"] = user_id
        return response.sql, parameters


def build_default_sql_planner() -> "LangChainOpenAISQLPlanner | None":
    """Select the configured SQL planner without making offline startup fail.

    The SQL subgraph remains deterministic when credentials are absent or the
    optional LangChain OpenAI package is unavailable.  Only safe provider
    metadata is exposed by callers; this function never logs the key.
    """

    from app.runtime.config import RuntimeConfig

    if not RuntimeConfig.from_env().openai_api_key_configured:
        return None
    try:
        return LangChainOpenAISQLPlanner.from_env()
    except Exception:  # noqa: BLE001 - provider setup must not break local startup.
        return None
