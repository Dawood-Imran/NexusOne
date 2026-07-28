"""Local HTTP integration contracts with no Postgres, OpenAI, or browser service."""

from __future__ import annotations

import json
import os
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

from app.actions.audit_service import AuditService, InMemoryAuditRepository
from app.actions.feedback_service import FeedbackService, InMemoryFeedbackRepository
from app.agents.orchestrator.answer_composer import DeterministicAnswerComposer
from app.agents.sql_subgraph.state import SQLExecutionResult
from tests.unit.agents.orchestrator.intent_fixtures import fixture_classifier
from app.api.dev_server import NexusOneRequestHandler
from app.services.chat_service import ChatService


class LocalHTTPProductSurfaceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.environment = patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "",
                "DATABASE_URL": "",
                "LANGSMITH_TRACING": "false",
                "LANGCHAIN_TRACING_V2": "false",
                "LANGSMITH_API_KEY": "",
            },
            clear=False,
        )
        cls.environment.start()
        cls.original_auth_service = NexusOneRequestHandler.auth_service
        cls.original_chat_service = NexusOneRequestHandler.service
        from app.auth.service import LocalAuthService

        cls.auth_service = LocalAuthService()
        cls.feedback_repository = InMemoryFeedbackRepository()
        cls.audit_repository = InMemoryAuditRepository()
        NexusOneRequestHandler.auth_service = cls.auth_service
        NexusOneRequestHandler.service = ChatService(
            answer_composer=DeterministicAnswerComposer(fallback_reason="OFFLINE_HTTP_TEST"),
            intent_classifier=fixture_classifier(),
            feedback_service=FeedbackService(cls.feedback_repository),
            audit_service=AuditService(cls.audit_repository),
        )
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
        cls.environment.stop()

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: Any = None,
        raw_body: str | None = None,
        cookie: str | None = None,
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        body = raw_body if raw_body is not None else json.dumps(payload if payload is not None else {})
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
        return response.status, response_headers, parsed

    def login(self, username: str = "u001") -> tuple[str, dict[str, Any]]:
        status, headers, payload = self.request(
            "POST",
            "/api/auth/login",
            payload={"username": username, "password": "nexusone-local-dev"},
        )
        self.assertEqual(200, status)
        return headers["set-cookie"].split(";", 1)[0], payload

    def test_public_http_chat_returns_citation_and_safe_capabilities(self) -> None:
        cookie, _ = self.login()

        status, _, payload = self.request(
            "POST",
            "/api/chat",
            payload={"message": "How do I request AWS access?", "include_trace": True},
            cookie=cookie,
        )

        self.assertEqual(200, status)
        self.assertEqual("answered", payload["status"])
        self.assertEqual("u001", payload["profile"]["user_id"])
        self.assertEqual("rag", payload["route"])
        self.assertIn("Create an IT access ticket", payload["message"])
        self.assertEqual("AWS Access Request", payload["citations"][0]["title"])
        self.assertEqual("validation_only", payload["capabilities"]["sql"]["mode"])
        self.assertEqual("deterministic", payload["capabilities"]["answer_composer"]["provider"])
        self.assertNotIn("fixture-secret", json.dumps(payload))

    def test_denied_http_chat_stops_before_retrieval_and_does_not_leak_title(self) -> None:
        cookie, _ = self.login()

        status, _, payload = self.request(
            "POST",
            "/api/chat",
            payload={"message": "What are the Q4 revenue risks?", "include_trace": True},
            cookie=cookie,
        )

        self.assertEqual(200, status)
        self.assertEqual("denied", payload["status"])
        self.assertEqual("ROLE_NOT_AUTHORIZED", payload["reason_code"])
        self.assertNotIn("Q4 Revenue Risk Register", json.dumps(payload))
        nodes = {step["node"] for step in payload["trace"]}
        self.assertNotIn("retrieve_rag_context", nodes)
        self.assertNotIn("run_sql_subgraph", nodes)

    def test_malformed_and_empty_chat_requests_have_bounded_errors(self) -> None:
        cookie, _ = self.login()

        malformed_status, _, malformed = self.request(
            "POST",
            "/api/chat",
            raw_body='{"message":',
            cookie=cookie,
        )
        empty_status, _, empty = self.request(
            "POST",
            "/api/chat",
            payload={"message": "   "},
            cookie=cookie,
        )

        self.assertEqual(400, malformed_status)
        self.assertEqual("Invalid JSON payload.", malformed["message"])
        self.assertEqual(200, empty_status)
        self.assertEqual("error", empty["status"])
        self.assertEqual("EMPTY_MESSAGE", empty["reason_code"])
        self.assertNotIn("Traceback", json.dumps(empty))

    def test_two_authenticated_users_receive_owner_scoped_ticket_lists(self) -> None:
        original_service = NexusOneRequestHandler.service
        NexusOneRequestHandler.service = ChatService(
            sql_executor=_AuthenticatedTicketListExecutor(),
            answer_composer=DeterministicAnswerComposer(fallback_reason="OFFLINE_HTTP_TEST"),
            intent_classifier=fixture_classifier(),
            feedback_service=FeedbackService(self.feedback_repository),
            audit_service=AuditService(self.audit_repository),
        )
        try:
            employee_cookie, _ = self.login("u001")
            manager_cookie, _ = self.login("u002")
            employee_status, _, employee = self.request(
                "POST",
                "/api/chat",
                payload={"message": "Show my ticket status."},
                cookie=employee_cookie,
            )
            manager_status, _, manager = self.request(
                "POST",
                "/api/chat",
                payload={"message": "Show my ticket status."},
                cookie=manager_cookie,
            )
        finally:
            NexusOneRequestHandler.service = original_service

        self.assertEqual(200, employee_status)
        self.assertEqual(200, manager_status)
        self.assertEqual("u001", employee["profile"]["user_id"])
        self.assertEqual("u002", manager["profile"]["user_id"])
        self.assertEqual(["IT-9001"], [row["ticket_id"] for row in employee["rows"]])
        self.assertEqual({"IT-9001", "IT-9002"}, {row["ticket_id"] for row in manager["rows"]})
        self.assertNotIn("HR-9003", json.dumps(employee))
        self.assertNotIn("requester_id", json.dumps(employee))

    def test_ticket_action_http_happy_path_returns_sanitized_ticket(self) -> None:
        cookie, _ = self.login()

        status, _, payload = self.request(
            "POST",
            "/api/chat",
            payload={"message": "Create an IT ticket for AWS sandbox access needed for billing migration."},
            cookie=cookie,
        )

        self.assertEqual(200, status)
        self.assertEqual("ticket_created", payload["status"])
        self.assertEqual("ticket_create", payload["route"])
        self.assertTrue(payload["ticket"]["ticket_id"].startswith("IT-"))
        self.assertNotIn("requester_id", json.dumps(payload))
        self.assertNotIn("assigned_to", json.dumps(payload))

    def test_provider_failure_falls_back_to_safe_deterministic_http_answer(self) -> None:
        original_service = NexusOneRequestHandler.service
        NexusOneRequestHandler.service = ChatService(
            answer_composer=_ExplodingComposer(),
            intent_classifier=fixture_classifier(),
            feedback_service=FeedbackService(self.feedback_repository),
            audit_service=AuditService(self.audit_repository),
        )
        try:
            cookie, _ = self.login()
            status, _, payload = self.request(
                "POST",
                "/api/chat",
                payload={"message": "How do I request AWS access?"},
                cookie=cookie,
            )
        finally:
            NexusOneRequestHandler.service = original_service

        self.assertEqual(200, status)
        self.assertEqual("answered", payload["status"])
        self.assertIn("Create an IT access ticket", payload["message"])
        self.assertIn("after_provider_error", payload["model_backend"])
        self.assertNotIn("secret provider failure", json.dumps(payload))

    def test_no_provider_general_question_is_explicit_no_answer(self) -> None:
        cookie, _ = self.login()

        status, _, payload = self.request(
            "POST",
            "/api/chat",
            payload={"message": "What is quantum computing?"},
            cookie=cookie,
        )

        self.assertEqual(200, status)
        self.assertEqual("no_answer", payload["status"])
        self.assertEqual("GENERAL_KNOWLEDGE", payload["route"])
        self.assertIn("reliable local answer", payload["message"])
        self.assertEqual("deterministic", payload["capabilities"]["answer_composer"]["provider"])

    def test_invalid_feedback_is_rejected_and_retry_is_bounded(self) -> None:
        cookie, _ = self.login()

        invalid_status, _, invalid = self.request(
            "POST",
            "/api/feedback",
            payload={"rating": "leaked_salary"},
            cookie=cookie,
        )
        first_status, _, first = self.request(
            "POST",
            "/api/feedback",
            payload={"rating": "helpful", "comment": "  useful   source  "},
            cookie=cookie,
        )
        retry_status, _, retry = self.request(
            "POST",
            "/api/feedback",
            payload={"rating": "helpful", "comment": "  useful   source  "},
            cookie=cookie,
        )

        self.assertEqual(400, invalid_status)
        self.assertEqual("INVALID_FEEDBACK_RATING", invalid["reason_code"])
        self.assertEqual(200, first_status)
        self.assertEqual(200, retry_status)
        self.assertEqual("stored", first["status"])
        self.assertEqual(first["feedback_id"] + 1, retry["feedback_id"])
        self.assertEqual("useful source", self.feedback_repository.rows[-1]["comment"])

    def test_missing_credentials_invalid_cookie_and_unknown_path_are_safe(self) -> None:
        login_status, headers, login = self.request(
            "POST",
            "/api/auth/login",
            payload={"username": "u001"},
        )
        session_status, _, session = self.request(
            "GET",
            "/api/auth/session",
            cookie="nexusone_session=not-a-live-session",
        )
        not_found_status, _, not_found = self.request("GET", "/api/does-not-exist")

        self.assertEqual(401, login_status)
        self.assertEqual("INVALID_CREDENTIALS", login["reason_code"])
        self.assertNotIn("set-cookie", headers)
        self.assertEqual(401, session_status)
        self.assertEqual("AUTHENTICATION_REQUIRED", session["reason_code"])
        self.assertEqual(404, not_found_status)
        self.assertEqual("Not found.", not_found["message"])

    def test_feedback_identity_cannot_be_changed_by_body_retry(self) -> None:
        cookie, _ = self.login("u001")

        status, _, payload = self.request(
            "POST",
            "/api/feedback",
            payload={"user_id": "u006", "rating": "helpful"},
            cookie=cookie,
        )

        self.assertEqual(403, status)
        self.assertEqual("IDENTITY_MISMATCH", payload["reason_code"])
        self.assertNotIn("u006", json.dumps(payload))


class _AuthenticatedTicketListExecutor:
    rows = (
        {"ticket_id": "IT-9001", "requester_id": "u001", "department": "it", "category": "battery", "priority": "normal", "status": "open", "updated_at": "2026-02-07T09:00:00+00:00"},
        {"ticket_id": "IT-9002", "requester_id": "u002", "department": "it", "category": "vpn", "priority": "high", "status": "in_progress", "updated_at": "2026-02-08T09:00:00+00:00"},
        {"ticket_id": "HR-9003", "requester_id": "u003", "department": "hr", "category": "payroll", "priority": "normal", "status": "open", "updated_at": "2026-02-09T09:00:00+00:00"},
    )

    def fetch_one(self, query, parameters):
        return None

    def fetch_all(self, query, parameters, max_rows):
        user_id = parameters["user_id"]
        requesters = {"u001"} if user_id == "u001" else {"u001", "u002"} if user_id == "u002" else {user_id}
        visible = [row for row in self.rows if row["requester_id"] in requesters]
        return SQLExecutionResult(
            columns=tuple(visible[0].keys()) if visible else ("ticket_id", "status", "updated_at"),
            rows=tuple(visible[:max_rows]),
            row_count=len(visible[:max_rows]),
            elapsed_ms=1,
        )


class _ExplodingComposer:
    def compose(self, context):
        raise RuntimeError("secret provider failure")


if __name__ == "__main__":
    unittest.main()
