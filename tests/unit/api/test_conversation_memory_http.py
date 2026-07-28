from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app.agents.orchestrator.answer_composer import DeterministicAnswerComposer
from app.api.dev_server import NexusOneRequestHandler
from app.auth.service import LocalAuthService
from app.memory.conversation_store import SQLiteConversationStore
from app.memory.user_memory import JSONUserMemoryStore
from app.services.chat_service import ChatService
from tests.unit.agents.orchestrator.intent_fixtures import fixture_classifier


class ConversationMemoryHTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.environment = patch.dict(os.environ, {"OPENAI_API_KEY": "", "DATABASE_URL": ""}, clear=True)
        cls.environment.start()
        cls.directory = tempfile.TemporaryDirectory()
        cls.original_auth_service = NexusOneRequestHandler.auth_service
        cls.original_chat_service = NexusOneRequestHandler.service
        NexusOneRequestHandler.auth_service = LocalAuthService()
        cls.service = ChatService(
            conversation_store=SQLiteConversationStore(Path(cls.directory.name) / "conversations.sqlite3"),
            user_memory_store=JSONUserMemoryStore(Path(cls.directory.name) / "profiles"),
            answer_composer=DeterministicAnswerComposer(),
            intent_classifier=fixture_classifier(),
        )
        NexusOneRequestHandler.service = cls.service
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), NexusOneRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        NexusOneRequestHandler.auth_service = cls.original_auth_service
        NexusOneRequestHandler.service = cls.original_chat_service
        cls.directory.cleanup()
        cls.environment.stop()

    def request(self, method: str, path: str, *, payload=None, cookie=None, accept="application/json"):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        headers = {"Content-Type": "application/json", "Accept": accept}
        if cookie:
            headers["Cookie"] = cookie
        connection.request(method, path, body=json.dumps(payload if payload is not None else {}), headers=headers)
        response = connection.getresponse()
        raw = response.read()
        result_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        return response.status, result_headers, raw

    def login(self, username: str = "u001") -> str:
        status, headers, _ = self.request(
            "POST", "/api/auth/login", payload={"username": username, "password": "nexusone-local-dev"}
        )
        self.assertEqual(200, status)
        return headers["set-cookie"].split(";", 1)[0]

    def json_request(self, method: str, path: str, *, payload=None, cookie=None):
        status, headers, raw = self.request(method, path, payload=payload, cookie=cookie)
        return status, headers, json.loads(raw.decode("utf-8")) if raw else {}

    def test_server_id_reload_isolation_and_replay(self) -> None:
        cookie = self.login()
        first_status, _, first = self.json_request(
            "POST", "/api/chat", payload={"message": "How do I request AWS access?"}, cookie=cookie
        )
        self.assertEqual(200, first_status)
        conversation_id = first["conversation_id"]
        turn_id = first["turn_id"]
        self.assertRegex(conversation_id, r"^[0-9a-f-]{36}$")
        self.assertRegex(turn_id, r"^[0-9a-f-]{36}$")

        second_status, _, second = self.json_request(
            "POST",
            "/api/chat",
            payload={"conversation_id": conversation_id, "message": "What did I ask earlier?"},
            cookie=cookie,
        )
        self.assertEqual(200, second_status)
        self.assertIn("AWS access", second["message"])

        replay_status, _, replay = self.json_request(
            "POST",
            "/api/chat",
            payload={"conversation_id": conversation_id, "turn_id": turn_id, "message": "How do I request AWS access?"},
            cookie=cookie,
        )
        self.assertEqual(200, replay_status)
        self.assertEqual(first["message"], replay["message"])
        self.assertEqual(first["turn_id"], replay["turn_id"])

        list_status, _, listing = self.json_request("GET", "/api/conversations", cookie=cookie)
        self.assertEqual(200, list_status)
        record = next(item for item in listing["conversations"] if item["conversation_id"] == conversation_id)
        self.assertEqual(2, record["turn_count"])
        self.assertEqual(2, len(record["turns"]))

        other_cookie = self.login("u002")
        denied_status, _, denied = self.json_request(
            "GET", f"/api/conversations/{conversation_id}", cookie=other_cookie
        )
        self.assertEqual(404, denied_status)
        self.assertEqual("CONVERSATION_NOT_FOUND", denied["reason_code"])

    def test_malformed_and_unknown_conversation_ids_are_safe(self) -> None:
        cookie = self.login()
        malformed_status, _, malformed = self.json_request(
            "POST", "/api/chat", payload={"conversation_id": "../u002", "message": "Hello"}, cookie=cookie
        )
        self.assertEqual(400, malformed_status)
        self.assertEqual("MALFORMED_CONVERSATION_ID", malformed["reason_code"])
        empty_status, _, empty = self.json_request(
            "POST", "/api/chat", payload={"conversation_id": "", "message": "Hello"}, cookie=cookie
        )
        self.assertEqual(400, empty_status)
        self.assertEqual("MALFORMED_CONVERSATION_ID", empty["reason_code"])
        unknown_status, _, unknown = self.json_request(
            "POST", "/api/chat", payload={"conversation_id": "missing-conversation", "message": "Hello"}, cookie=cookie
        )
        self.assertEqual(404, unknown_status)
        self.assertEqual("CONVERSATION_NOT_FOUND", unknown["reason_code"])

    def test_sse_start_and_completion_share_server_ids(self) -> None:
        cookie = self.login()
        status, headers, raw = self.request(
            "POST", "/api/chat", payload={"message": "How do I request AWS access?"}, cookie=cookie, accept="text/event-stream"
        )
        self.assertEqual(200, status)
        self.assertTrue(headers["content-type"].startswith("text/event-stream"))
        events = []
        for frame in raw.decode("utf-8").strip().split("\n\n"):
            data = next(line[5:].strip() for line in frame.splitlines() if line.startswith("data:"))
            events.append(json.loads(data))
        self.assertEqual("response.start", events[0]["type"])
        self.assertEqual("response.complete", events[-1]["type"])
        self.assertEqual(events[0]["conversation_id"], events[-1]["response"]["conversation_id"])
        self.assertEqual(events[0]["turn_id"], events[-1]["response"]["turn_id"])


if __name__ == "__main__":
    unittest.main()
