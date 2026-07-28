from __future__ import annotations

import concurrent.futures
import json
import tempfile
import unittest
from pathlib import Path

from app.memory.conversation_store import (
    ConversationNotFound,
    IdempotencyConflict,
    InvalidConversationId,
    InvalidTurnId,
    SQLiteConversationStore,
    TurnInProgress,
)


class SQLiteConversationStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.store = SQLiteConversationStore(Path(self.directory.name) / "conversations.sqlite3", max_history_turns=2)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_creates_owner_scoped_conversation_and_bounded_history(self) -> None:
        conversation = self.store.create_conversation("u001")
        for index in range(4):
            reservation = self.store.begin_turn("u001", conversation.conversation_id, f"turn-{index}", f"Question {index}")
            self.store.complete_turn("u001", reservation.conversation_id, reservation.turn_id, {"status": "answered", "message": f"Answer {index}"})

        latest = self.store.begin_turn("u001", conversation.conversation_id, "turn-new", "Question new")

        self.assertEqual(conversation.conversation_id, latest.conversation_id)
        self.assertEqual(["Question 2", "Question 3"], [item["user_message"] for item in latest.history])
        record = self.store.get_conversation("u001", conversation.conversation_id)
        self.assertEqual(5, record.turn_count)
        self.assertEqual(2, len(record.turns))

    def test_unknown_and_other_owner_ids_are_not_readable_or_appendable(self) -> None:
        conversation = self.store.create_conversation("u001")
        with self.assertRaises(ConversationNotFound):
            self.store.get_conversation("u002", conversation.conversation_id)
        with self.assertRaises(ConversationNotFound):
            self.store.begin_turn("u002", conversation.conversation_id, "turn-1", "secret")
        with self.assertRaises(ConversationNotFound):
            self.store.get_conversation("u001", "missing-conversation")

    def test_malformed_ids_fail_closed(self) -> None:
        with self.assertRaises(InvalidConversationId):
            self.store.begin_turn("u001", "../u002", None, "hello")
        conversation = self.store.create_conversation("u001")
        with self.assertRaises(InvalidConversationId):
            self.store.get_conversation("u001", "bad/id")
        with self.assertRaises(InvalidTurnId):
            self.store.begin_turn("u001", conversation.conversation_id, "bad/id", "hello")

    def test_replay_is_idempotent_and_reuse_with_different_text_conflicts(self) -> None:
        conversation = self.store.create_conversation("u001")
        first = self.store.begin_turn("u001", conversation.conversation_id, "turn-1", "same text")
        response = {"status": "answered", "message": "same response"}
        self.store.complete_turn("u001", first.conversation_id, first.turn_id, response)
        replay = self.store.begin_turn("u001", conversation.conversation_id, "turn-1", "same text")
        self.assertTrue(replay.is_replay)
        self.assertEqual(response, dict(replay.replay_response or {}))
        with self.assertRaises(IdempotencyConflict):
            self.store.begin_turn("u001", conversation.conversation_id, "turn-1", "different text")

    def test_pending_duplicate_is_rejected(self) -> None:
        conversation = self.store.create_conversation("u001")
        self.store.begin_turn("u001", conversation.conversation_id, "turn-1", "same text")
        with self.assertRaises(TurnInProgress):
            self.store.begin_turn("u001", conversation.conversation_id, "turn-1", "same text")

    def test_concurrent_new_turns_receive_unique_sequences(self) -> None:
        conversation = self.store.create_conversation("u001")

        def append(index: int) -> None:
            reservation = self.store.begin_turn("u001", conversation.conversation_id, f"turn-{index}", f"Question {index}")
            self.store.complete_turn("u001", reservation.conversation_id, reservation.turn_id, {"message": f"Answer {index}"})

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(append, range(8)))

        record = self.store.get_conversation("u001", conversation.conversation_id)
        self.assertEqual(8, record.turn_count)
        self.assertEqual([7, 8], [turn.sequence for turn in record.turns])


if __name__ == "__main__":
    unittest.main()
