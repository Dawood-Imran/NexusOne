"""Framework-independent chat service for NexusOne Copilot."""

from __future__ import annotations

from typing import Any

from app.agents.orchestrator import NexusOneOrchestrator
from app.agents.orchestrator.answer_composer import AnswerComposer
from app.agents.sql_subgraph.state import SQLExecutor
from app.auth.profiles import list_profiles
from app.retrieval.chunk_index import MetadataChunkRetriever
from app.retrieval.local_kb import LocalKBRetriever


class ChatService:
    """Web/API facade over the main LangGraph orchestrator."""

    def __init__(
        self,
        retriever: LocalKBRetriever | None = None,
        chunk_retriever: MetadataChunkRetriever | None = None,
        sql_executor: SQLExecutor | None = None,
        sql_planner: Any | None = None,
        answer_composer: AnswerComposer | None = None,
    ) -> None:
        self.retriever = retriever or LocalKBRetriever()
        self.chunk_retriever = chunk_retriever or MetadataChunkRetriever()
        self.sql_executor = sql_executor
        self.orchestrator = NexusOneOrchestrator(
            chunk_retriever=self.chunk_retriever,
            local_retriever=self.retriever,
            sql_executor=sql_executor,
            sql_planner=sql_planner,
            answer_composer=answer_composer,
        )

    def profiles(self) -> list[dict[str, object]]:
        return list_profiles()

    def handle_message(self, user_id: str, message: str, include_trace: bool = False) -> dict[str, Any]:
        return dict(
            self.orchestrator.invoke(
                {
                    "conversation_id": "web-chat",
                    "turn_id": "web-turn",
                    "user_id": user_id,
                    "message": message,
                    "include_trace": include_trace,
                    "execute_sql": self.sql_executor is not None,
                }
            )
        )
