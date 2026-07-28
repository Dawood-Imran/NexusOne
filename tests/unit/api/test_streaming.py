import json
import threading
import unittest
from http.client import HTTPConnection
from typing import Any

from http.server import ThreadingHTTPServer

from app.api.dev_server import NexusOneRequestHandler, _ClientDisconnected
from app.api.streaming import encode_sse_event
from app.auth.service import LocalAuthService


class StreamContractChatService:
    def stream_authenticated_message(
        self,
        session: Any,
        message: str,
        include_trace: bool = False,
    ):
        yield {"type": "response.delta", "delta": "A streamed "}
        yield {"type": "response.delta", "delta": "answer."}
        yield {
            "type": "response.complete",
            "response": {
                "status": "answered",
                "reason_code": "FIXTURE",
                "route": "rag",
                "message": "A streamed answer.",
                "citations": [{"reference_id": 1, "title": "Approved source"}],
                "trace": [{"node": "finalize_response", "status": "answered"}],
                "profile": session.safe_user,
                "conversation_id": "web-chat",
                "turn_id": "web-turn",
            },
        }


class ErrorStreamChatService:
    def stream_authenticated_message(self, session: Any, message: str, include_trace: bool = False):
        yield {
            "type": "response.error",
            "reason_code": "STREAM_ERROR",
            "message": "We could not complete that request. Try again in a moment.",
            "recoverable": False,
        }


class _BrokenPipeWriter:
    def write(self, value: bytes) -> None:
        raise BrokenPipeError

    def flush(self) -> None:
        return


class StreamingHTTPContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original_auth_service = NexusOneRequestHandler.auth_service
        cls.original_chat_service = NexusOneRequestHandler.service
        NexusOneRequestHandler.auth_service = LocalAuthService()
        NexusOneRequestHandler.service = StreamContractChatService()
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

    def request(self, *, service: Any | None = None) -> tuple[int, dict[str, str], bytes]:
        if service is not None:
            NexusOneRequestHandler.service = service
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(
            "POST",
            "/api/auth/login",
            body=json.dumps({"username": "u001", "password": "nexusone-local-dev"}),
            headers={"Content-Type": "application/json"},
        )
        login = connection.getresponse()
        cookie = login.getheader("Set-Cookie").split(";", 1)[0]
        login.read()
        connection.close()

        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request(
            "POST",
            "/api/chat",
            body=json.dumps({"message": "How do I request AWS access?", "include_trace": True}),
            headers={
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
                "Cookie": cookie,
            },
        )
        response = connection.getresponse()
        headers = {key.lower(): value for key, value in response.getheaders()}
        raw = response.read()
        connection.close()
        return response.status, headers, raw

    @staticmethod
    def parse_events(raw: bytes) -> list[dict[str, Any]]:
        events = []
        for frame in raw.decode("utf-8").strip().split("\n\n"):
            lines = frame.splitlines()
            event_name = next(line.split(":", 1)[1].strip() for line in lines if line.startswith("event:"))
            data = next(line.split(":", 1)[1].strip() for line in lines if line.startswith("data:"))
            payload = json.loads(data)
            if payload["type"] != event_name:
                raise AssertionError("SSE name and JSON type differ")
            events.append(payload)
        return events

    def test_stream_orders_deltas_before_complete_and_preserves_metadata(self) -> None:
        status, headers, raw = self.request(service=StreamContractChatService())

        self.assertEqual(200, status)
        self.assertTrue(headers["content-type"].startswith("text/event-stream"))
        self.assertEqual("no-cache, no-store", headers["cache-control"])
        events = self.parse_events(raw)
        self.assertEqual(
            ["response.start", "response.delta", "response.delta", "response.complete"],
            [event["type"] for event in events],
        )
        complete = events[-1]["response"]
        deltas = "".join(event["delta"] for event in events if event["type"] == "response.delta")
        self.assertEqual("A streamed answer.", deltas)
        self.assertEqual(deltas, complete["message"])
        self.assertEqual("Approved source", complete["citations"][0]["title"])
        self.assertEqual("finalize_response", complete["trace"][0]["node"])

    def test_stream_emits_typed_terminal_error_without_internal_details(self) -> None:
        status, _, raw = self.request(service=ErrorStreamChatService())

        self.assertEqual(200, status)
        events = self.parse_events(raw)
        self.assertEqual(["response.start", "response.error"], [event["type"] for event in events])
        self.assertFalse(events[-1]["recoverable"])
        self.assertEqual("STREAM_ERROR", events[-1]["reason_code"])
        self.assertNotIn("Traceback", raw.decode("utf-8"))

    def test_disconnect_is_translated_to_cancellation(self) -> None:
        handler = object.__new__(NexusOneRequestHandler)
        handler.wfile = _BrokenPipeWriter()

        with self.assertRaises(_ClientDisconnected):
            handler._send_stream_event({"type": "response.delta", "delta": "partial"})

    def test_event_framing_rejects_unknown_types(self) -> None:
        with self.assertRaises(ValueError):
            encode_sse_event("internal.graph_state", {"prompt": "must not be sent"})


if __name__ == "__main__":
    unittest.main()
