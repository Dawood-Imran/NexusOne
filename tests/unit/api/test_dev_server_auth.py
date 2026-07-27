import json
import threading
import unittest
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from typing import Any

from app.api.dev_server import NexusOneRequestHandler
from app.auth.service import LocalAuthService
from http.server import ThreadingHTTPServer


class ContractChatService:
    """Minimal service double; auth behavior is the focus of this contract test."""

    def handle_authenticated_message(self, session: Any, message: str, include_trace: bool = False) -> dict[str, Any]:
        return {
            "status": "answered",
            "message": "Synthetic response.",
            "profile": session.safe_user,
            "include_trace": include_trace,
            "message_received": message,
        }

    def submit_authenticated_feedback(
        self,
        session: Any,
        *,
        conversation_id: str,
        turn_id: str,
        rating: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        return {"status": "stored", "feedback_id": 1, "user_id": session.user_id, "rating": rating}


class DevServerAuthenticationContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original_auth_service = NexusOneRequestHandler.auth_service
        cls.original_chat_service = NexusOneRequestHandler.service
        NexusOneRequestHandler.auth_service = LocalAuthService()
        NexusOneRequestHandler.service = ContractChatService()
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

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        cookie: str | None = None,
    ) -> tuple[int, dict[str, str], dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        body = json.dumps(payload or {})
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        response_headers = {key.lower(): value for key, value in response.getheaders()}
        connection.close()
        parsed = json.loads(raw.decode("utf-8")) if raw else {}
        return response.status, response_headers, parsed

    @staticmethod
    def cookie_from(headers: dict[str, str]) -> str:
        cookies = SimpleCookie()
        cookies.load(headers["set-cookie"])
        return cookies["nexusone_session"].OutputString()

    def login(self, username: str = "u001") -> tuple[str, dict[str, Any]]:
        status, headers, payload = self.request(
            "POST",
            "/api/auth/login",
            payload={"username": username, "password": "nexusone-local-dev"},
        )
        self.assertEqual(200, status)
        return self.cookie_from(headers), payload

    def test_valid_login_returns_safe_user_and_http_only_cookie(self) -> None:
        status, headers, payload = self.request(
            "POST",
            "/api/auth/login",
            payload={"username": "u001", "password": "nexusone-local-dev"},
        )

        self.assertEqual(200, status)
        self.assertEqual("authenticated", payload["status"])
        self.assertEqual("u001", payload["user"]["user_id"])
        self.assertEqual("employee", payload["user"]["role"])
        self.assertNotIn("email", payload["user"])
        self.assertNotIn("groups", payload["user"])
        self.assertNotIn("password", json.dumps(payload).lower())
        self.assertIn("httponly", headers["set-cookie"].lower())
        self.assertIn("samesite=lax", headers["set-cookie"].lower())

    def test_invalid_credentials_are_generic_and_do_not_set_a_session(self) -> None:
        status, headers, payload = self.request(
            "POST",
            "/api/auth/login",
            payload={"username": "u001", "password": "wrong-password"},
        )

        self.assertEqual(401, status)
        self.assertEqual("INVALID_CREDENTIALS", payload["reason_code"])
        self.assertNotIn("set-cookie", headers)
        self.assertNotIn("u001", json.dumps(payload))

    def test_session_persists_for_current_session_and_chat(self) -> None:
        cookie, login_payload = self.login()

        status, _, current = self.request("GET", "/api/auth/session", cookie=cookie)
        self.assertEqual(200, status)
        self.assertEqual(login_payload["user"], current["user"])

        status, _, response = self.request(
            "POST",
            "/api/chat",
            payload={"message": "How do I request AWS access?"},
            cookie=cookie,
        )
        self.assertEqual(200, status)
        self.assertEqual("u001", response["profile"]["user_id"])
        self.assertEqual("employee", response["profile"]["role"])

    def test_logout_invalidates_session_and_clears_cookie(self) -> None:
        cookie, _ = self.login()

        status, headers, payload = self.request("POST", "/api/auth/logout", cookie=cookie)
        self.assertEqual(200, status)
        self.assertEqual({"status": "signed_out"}, payload)
        self.assertIn("max-age=0", headers["set-cookie"].lower())

        status, _, current = self.request("GET", "/api/auth/session", cookie=cookie)
        self.assertEqual(401, status)
        self.assertEqual("AUTHENTICATION_REQUIRED", current["reason_code"])

    def test_chat_and_feedback_reject_unauthenticated_requests(self) -> None:
        chat_status, _, chat = self.request("POST", "/api/chat", payload={"message": "Hello"})
        feedback_status, _, feedback = self.request(
            "POST",
            "/api/feedback",
            payload={"rating": "helpful", "user_id": "u001"},
        )

        self.assertEqual(401, chat_status)
        self.assertEqual(401, feedback_status)
        self.assertEqual("AUTHENTICATION_REQUIRED", chat["reason_code"])
        self.assertEqual("AUTHENTICATION_REQUIRED", feedback["reason_code"])

    def test_body_user_id_cannot_impersonate_another_account(self) -> None:
        cookie, _ = self.login("u001")

        chat_status, _, chat = self.request(
            "POST",
            "/api/chat",
            payload={"user_id": "u006", "message": "What are the Q4 revenue risks?"},
            cookie=cookie,
        )
        feedback_status, _, feedback = self.request(
            "POST",
            "/api/feedback",
            payload={"user_id": "u006", "rating": "helpful"},
            cookie=cookie,
        )

        self.assertEqual(403, chat_status)
        self.assertEqual(403, feedback_status)
        self.assertEqual("IDENTITY_MISMATCH", chat["reason_code"])
        self.assertEqual("IDENTITY_MISMATCH", feedback["reason_code"])
        self.assertNotIn("Q4 Revenue Risk", json.dumps(chat))

    def test_role_and_profile_body_fields_cannot_change_session_identity(self) -> None:
        cookie, _ = self.login("u001")

        status, _, response = self.request(
            "POST",
            "/api/chat",
            payload={
                "user_id": "u001",
                "role": "ceo",
                "profile": {"user_id": "u006", "role": "ceo"},
                "message": "How do I request AWS access?",
            },
            cookie=cookie,
        )

        self.assertEqual(200, status)
        self.assertEqual("u001", response["profile"]["user_id"])
        self.assertEqual("employee", response["profile"]["role"])
        self.assertNotIn("email", response["profile"])
        self.assertNotIn("groups", response["profile"])

    def test_profile_list_is_not_an_authenticated_identity_boundary(self) -> None:
        status, _, payload = self.request("GET", "/api/profiles")

        self.assertEqual(404, status)
        self.assertEqual("error", payload["status"])


if __name__ == "__main__":
    unittest.main()
