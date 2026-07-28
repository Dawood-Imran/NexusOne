"""Replaceable local persistence boundary for conversation short-term memory.

The graph in this repository is a compiled ``StateGraph`` without a configured
LangGraph checkpointer.  This module provides the equivalent repository-owned
thread/checkpoint boundary: a conversation is an owner-scoped thread, each
turn is atomically reserved and completed in SQLite, and bounded prior turns
are loaded before graph invocation.  ``thread_id`` is still passed to the
LangGraph config by the orchestrator so a production checkpointer can replace
this store without changing the HTTP contract.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol


MAX_MESSAGE_CHARS = 2_000
MAX_HISTORY_TURNS = 8
MAX_HISTORY_TEXT_CHARS = 600
MAX_CONVERSATIONS = 50
MAX_STORED_TURNS = 100
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class ConversationMemoryError(Exception):
    """Base class for safe conversation persistence errors."""


class InvalidConversationId(ConversationMemoryError):
    """The supplied conversation identifier is malformed."""


class InvalidTurnId(ConversationMemoryError):
    """The supplied turn identifier is malformed."""


class ConversationNotFound(ConversationMemoryError):
    """The conversation does not exist for the authenticated owner."""


class IdempotencyConflict(ConversationMemoryError):
    """A turn identifier was reused for different user text."""


class TurnInProgress(ConversationMemoryError):
    """A duplicate request is already being processed."""


@dataclass(frozen=True)
class ConversationTurn:
    conversation_id: str
    turn_id: str
    owner_user_id: str
    sequence: int
    user_message: str
    assistant_message: str
    response: Mapping[str, Any] | None
    status: str
    created_at: str
    updated_at: str

    def to_public_dict(self) -> dict[str, Any]:
        """Return a bounded owner-visible record for reload/reconnect."""

        return {
            "turn_id": self.turn_id,
            "sequence": self.sequence,
            "user_message": self.user_message,
            "response": dict(self.response) if isinstance(self.response, Mapping) else None,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class ConversationRecord:
    conversation_id: str
    owner_user_id: str
    title: str
    created_at: str
    updated_at: str
    turn_count: int
    turns: tuple[ConversationTurn, ...] = ()

    def to_public_dict(self, *, include_turns: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "turn_count": self.turn_count,
        }
        if include_turns:
            result["turns"] = [turn.to_public_dict() for turn in self.turns]
        return result


@dataclass(frozen=True)
class TurnReservation:
    """Atomic turn reservation and the context preceding it."""

    conversation_id: str
    turn_id: str
    history: tuple[dict[str, str], ...]
    replay_response: Mapping[str, Any] | None = None

    @property
    def is_replay(self) -> bool:
        return self.replay_response is not None


class ConversationStore(Protocol):
    """Persistence interface that can be replaced by a production backend."""

    def create_conversation(self, owner_user_id: str) -> ConversationRecord: ...

    def begin_turn(
        self,
        owner_user_id: str,
        conversation_id: str | None,
        turn_id: str | None,
        user_message: str,
    ) -> TurnReservation: ...

    def complete_turn(
        self,
        owner_user_id: str,
        conversation_id: str,
        turn_id: str,
        response: Mapping[str, Any],
    ) -> None: ...

    def list_conversations(self, owner_user_id: str) -> tuple[ConversationRecord, ...]: ...

    def get_conversation(self, owner_user_id: str, conversation_id: str) -> ConversationRecord: ...

    def delete_conversation(self, owner_user_id: str, conversation_id: str) -> None: ...


class SQLiteConversationStore:
    """Local SQLite conversation store with owner checks and idempotent turns."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        max_history_turns: int = MAX_HISTORY_TURNS,
        max_conversations: int = MAX_CONVERSATIONS,
        max_stored_turns: int = MAX_STORED_TURNS,
    ) -> None:
        if max_history_turns <= 0 or max_history_turns > 50:
            raise ValueError("max_history_turns must be between 1 and 50")
        if max_conversations <= 0 or max_conversations > 500:
            raise ValueError("max_conversations must be between 1 and 500")
        if max_stored_turns <= 0 or max_stored_turns > 10_000:
            raise ValueError("max_stored_turns must be between 1 and 10000")
        self.database_path = Path(database_path).expanduser()
        self.max_history_turns = max_history_turns
        self.max_conversations = max_conversations
        self.max_stored_turns = max_stored_turns
        self._schema_lock = threading.Lock()
        self._ensure_schema()

    def create_conversation(self, owner_user_id: str) -> ConversationRecord:
        owner = _safe_owner(owner_user_id)
        conversation_id = str(uuid.uuid4())
        now = _now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO conversations (conversation_id, owner_user_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, owner, "New conversation", now, now),
            )
            connection.commit()
        return ConversationRecord(conversation_id, owner, "New conversation", now, now, 0)

    def begin_turn(
        self,
        owner_user_id: str,
        conversation_id: str | None,
        turn_id: str | None,
        user_message: str,
    ) -> TurnReservation:
        owner = _safe_owner(owner_user_id)
        message = _safe_message(user_message)
        requested_conversation_id = _safe_identifier(conversation_id, InvalidConversationId)
        requested_turn_id = _safe_identifier(turn_id, InvalidTurnId)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if requested_conversation_id is None:
                current_conversation_id = str(uuid.uuid4())
                now = _now()
                connection.execute(
                    """
                    INSERT INTO conversations (conversation_id, owner_user_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (current_conversation_id, owner, "New conversation", now, now),
                )
            else:
                current_conversation_id = requested_conversation_id
                row = connection.execute(
                    "SELECT owner_user_id FROM conversations WHERE conversation_id = ?",
                    (current_conversation_id,),
                ).fetchone()
                # Do not distinguish an unknown ID from another owner's ID.
                if row is None or row[0] != owner:
                    connection.rollback()
                    raise ConversationNotFound("conversation was not found")

            current_turn_id = requested_turn_id or str(uuid.uuid4())
            existing = connection.execute(
                """
                SELECT user_message, status, response_json
                FROM conversation_turns
                WHERE conversation_id = ? AND turn_id = ? AND owner_user_id = ?
                """,
                (current_conversation_id, current_turn_id, owner),
            ).fetchone()
            if existing is not None:
                existing_message, status, response_json = existing
                if existing_message != message:
                    connection.rollback()
                    raise IdempotencyConflict("turn_id cannot be reused for different text")
                if status == "complete" and response_json:
                    connection.commit()
                    return TurnReservation(
                        current_conversation_id,
                        current_turn_id,
                        (),
                        _decode_response(response_json),
                    )
                connection.rollback()
                raise TurnInProgress("turn is already in progress")

            sequence_row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence_no), 0) + 1
                FROM conversation_turns
                WHERE conversation_id = ? AND owner_user_id = ?
                """,
                (current_conversation_id, owner),
            ).fetchone()
            sequence = int(sequence_row[0])
            now = _now()
            connection.execute(
                """
                INSERT INTO conversation_turns
                    (conversation_id, owner_user_id, turn_id, sequence_no, user_message,
                     assistant_message, response_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, '', NULL, 'pending', ?, ?)
                """,
                (current_conversation_id, owner, current_turn_id, sequence, message, now, now),
            )
            if sequence == 1:
                title = _conversation_title(message)
                connection.execute(
                    "UPDATE conversations SET title = ?, updated_at = ? WHERE conversation_id = ? AND owner_user_id = ?",
                    (title, now, current_conversation_id, owner),
                )
            history = self._history(connection, owner, current_conversation_id)
            connection.commit()
        return TurnReservation(current_conversation_id, current_turn_id, history)

    def complete_turn(
        self,
        owner_user_id: str,
        conversation_id: str,
        turn_id: str,
        response: Mapping[str, Any],
    ) -> None:
        owner = _safe_owner(owner_user_id)
        current_conversation_id = _safe_identifier(conversation_id, InvalidConversationId)
        current_turn_id = _safe_identifier(turn_id, InvalidTurnId)
        if current_conversation_id is None or current_turn_id is None:
            raise InvalidConversationId("conversation and turn IDs are required")
        if not isinstance(response, Mapping):
            raise ValueError("response must be a mapping")
        serialized = json.dumps(dict(response), ensure_ascii=False, default=str)
        if len(serialized) > 200_000:
            raise ValueError("response is too large to persist")
        message = response.get("message")
        assistant_message = str(message)[:MAX_MESSAGE_CHARS] if message is not None else ""
        now = _now()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE conversation_turns
                SET assistant_message = ?, response_json = ?, status = 'complete', updated_at = ?
                WHERE conversation_id = ? AND owner_user_id = ? AND turn_id = ? AND status = 'pending'
                """,
                (
                    assistant_message,
                    serialized,
                    now,
                    current_conversation_id,
                    owner,
                    current_turn_id,
                ),
            )
            if cursor.rowcount != 1:
                row = connection.execute(
                    "SELECT 1 FROM conversation_turns WHERE conversation_id = ? AND owner_user_id = ? AND turn_id = ?",
                    (current_conversation_id, owner, current_turn_id),
                ).fetchone()
                connection.rollback()
                if row is None:
                    raise ConversationNotFound("turn was not found")
                return
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ? AND owner_user_id = ?",
                (now, current_conversation_id, owner),
            )
            latest_sequence = connection.execute(
                "SELECT MAX(sequence_no) FROM conversation_turns WHERE conversation_id = ? AND owner_user_id = ?",
                (current_conversation_id, owner),
            ).fetchone()[0]
            if latest_sequence is not None:
                cutoff = int(latest_sequence) - self.max_stored_turns + 1
                if cutoff > 1:
                    connection.execute(
                        "DELETE FROM conversation_turns WHERE conversation_id = ? AND owner_user_id = ? AND sequence_no < ?",
                        (current_conversation_id, owner, cutoff),
                    )
            connection.commit()

    def list_conversations(self, owner_user_id: str) -> tuple[ConversationRecord, ...]:
        owner = _safe_owner(owner_user_id)
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT conversation_id, owner_user_id, title, created_at, updated_at,
                       (SELECT COUNT(*) FROM conversation_turns t WHERE t.conversation_id = c.conversation_id) AS turn_count
                FROM conversations c
                WHERE owner_user_id = ?
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (owner, self.max_conversations),
            ).fetchall()
            return tuple(self._record_from_row(connection, row, include_turns=True) for row in rows)

    def get_conversation(self, owner_user_id: str, conversation_id: str) -> ConversationRecord:
        owner = _safe_owner(owner_user_id)
        current_conversation_id = _safe_identifier(conversation_id, InvalidConversationId)
        if current_conversation_id is None:
            raise InvalidConversationId("conversation ID is required")
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT conversation_id, owner_user_id, title, created_at, updated_at,
                       (SELECT COUNT(*) FROM conversation_turns t WHERE t.conversation_id = c.conversation_id) AS turn_count
                FROM conversations c
                WHERE conversation_id = ? AND owner_user_id = ?
                """,
                (current_conversation_id, owner),
            ).fetchone()
            if row is None:
                raise ConversationNotFound("conversation was not found")
            return self._record_from_row(connection, row, include_turns=True)

    def delete_conversation(self, owner_user_id: str, conversation_id: str) -> None:
        owner = _safe_owner(owner_user_id)
        current_conversation_id = _safe_identifier(conversation_id, InvalidConversationId)
        if current_conversation_id is None:
            raise InvalidConversationId("conversation ID is required")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "DELETE FROM conversations WHERE conversation_id = ? AND owner_user_id = ?",
                (current_conversation_id, owner),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise ConversationNotFound("conversation was not found")
            connection.commit()

    def _record_from_row(
        self,
        connection: sqlite3.Connection,
        row: Sequence[Any],
        *,
        include_turns: bool,
    ) -> ConversationRecord:
        turns: tuple[ConversationTurn, ...] = ()
        if include_turns:
            turn_rows = connection.execute(
                """
                SELECT conversation_id, turn_id, owner_user_id, sequence_no, user_message,
                       assistant_message, response_json, status, created_at, updated_at
                FROM conversation_turns
                WHERE conversation_id = ? AND owner_user_id = ?
                ORDER BY sequence_no DESC
                LIMIT ?
                """,
                (row[0], row[1], self.max_history_turns),
            ).fetchall()
            turns = tuple(_turn_from_row(turn_row) for turn_row in reversed(turn_rows))
        return ConversationRecord(
            conversation_id=str(row[0]),
            owner_user_id=str(row[1]),
            title=str(row[2]),
            created_at=str(row[3]),
            updated_at=str(row[4]),
            turn_count=int(row[5]),
            turns=turns,
        )

    def _history(
        self,
        connection: sqlite3.Connection,
        owner_user_id: str,
        conversation_id: str,
    ) -> tuple[dict[str, str], ...]:
        rows = connection.execute(
            """
            SELECT user_message, assistant_message
            FROM conversation_turns
            WHERE conversation_id = ? AND owner_user_id = ? AND status = 'complete'
            ORDER BY sequence_no DESC
            LIMIT ?
            """,
            (conversation_id, owner_user_id, self.max_history_turns),
        ).fetchall()
        return tuple(
            {
                "user_message": str(row[0])[:MAX_HISTORY_TEXT_CHARS],
                "assistant_message": str(row[1] or "")[:MAX_HISTORY_TEXT_CHARS],
            }
            for row in reversed(rows)
        )

    @contextmanager
    def _connection(self):
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path, timeout=30, isolation_level=None)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        with self._schema_lock:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS conversations (
                        conversation_id TEXT PRIMARY KEY,
                        owner_user_id TEXT NOT NULL,
                        title TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated
                        ON conversations(owner_user_id, updated_at DESC);
                    CREATE TABLE IF NOT EXISTS conversation_turns (
                        conversation_id TEXT NOT NULL,
                        owner_user_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        sequence_no INTEGER NOT NULL,
                        user_message TEXT NOT NULL,
                        assistant_message TEXT NOT NULL DEFAULT '',
                        response_json TEXT,
                        status TEXT NOT NULL CHECK(status IN ('pending', 'complete')),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (conversation_id, turn_id),
                        UNIQUE (conversation_id, sequence_no),
                        FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
                    );
                    CREATE INDEX IF NOT EXISTS idx_turns_owner_conversation
                        ON conversation_turns(owner_user_id, conversation_id, sequence_no);
                    """
                )


def _turn_from_row(row: Sequence[Any]) -> ConversationTurn:
    return ConversationTurn(
        conversation_id=str(row[0]),
        turn_id=str(row[1]),
        owner_user_id=str(row[2]),
        sequence=int(row[3]),
        user_message=str(row[4]),
        assistant_message=str(row[5] or ""),
        response=_decode_response(row[6]),
        status=str(row[7]),
        created_at=str(row[8]),
        updated_at=str(row[9]),
    )


def _decode_response(value: Any) -> Mapping[str, Any] | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return None
    return decoded if isinstance(decoded, Mapping) else None


def _safe_owner(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ConversationMemoryError("invalid conversation owner")
    return value.strip()


def _safe_message(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("message must be text")
    value = value.strip()
    if len(value) > MAX_MESSAGE_CHARS:
        raise ValueError("message is too long")
    return value


def _safe_identifier(value: Any, error_type: type[ConversationMemoryError]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise error_type("malformed identifier")
    return value


def _conversation_title(message: str) -> str:
    compact = re.sub(r"\s+", " ", message).strip()
    return compact[:57] + "..." if len(compact) > 60 else compact or "New conversation"


def _now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "ConversationMemoryError",
    "ConversationNotFound",
    "ConversationRecord",
    "ConversationStore",
    "ConversationTurn",
    "IdempotencyConflict",
    "InvalidConversationId",
    "InvalidTurnId",
    "MAX_HISTORY_TURNS",
    "MAX_STORED_TURNS",
    "SQLiteConversationStore",
    "TurnInProgress",
    "TurnReservation",
]
