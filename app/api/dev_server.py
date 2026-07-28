"""Small stdlib HTTP server for local NexusOne development.

Authentication is intentionally local-only.  The adapter owns the HTTP
contract while :mod:`app.auth.service` owns password verification and the
server-side session store.  See ``docs/authentication.md`` for request and
response shapes.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
from datetime import UTC, datetime
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping

from app.api.streaming import STREAM_CONTENT_TYPE, encode_sse_event
from app.auth.service import AuthenticatedSession, LocalAuthService
from app.memory.conversation_store import (
    ConversationMemoryError,
    ConversationNotFound,
    IdempotencyConflict,
    InvalidConversationId,
    InvalidTurnId,
    TurnInProgress,
)


ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = ROOT / "frontend" / "static"
SESSION_COOKIE_NAME = "nexusone_session"
DEFAULT_SESSION_TTL_SECONDS = 8 * 60 * 60


class _ClientDisconnected(Exception):
    """The browser closed an HTTP stream before the final event."""


def _session_ttl_seconds() -> int:
    raw_value = os.getenv("NEXUSONE_AUTH_SESSION_TTL_SECONDS")
    if raw_value is None:
        return DEFAULT_SESSION_TTL_SECONDS
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_SESSION_TTL_SECONDS
    return value if value > 0 else DEFAULT_SESSION_TTL_SECONDS


class NexusOneRequestHandler(BaseHTTPRequestHandler):
    """HTTP adapter with cookie-backed, server-owned identity."""

    # Lazily loaded so the stdlib authentication contract can be exercised
    # without importing the optional orchestration stack during auth-only tests.
    service: Any = None
    auth_service = LocalAuthService(session_ttl_seconds=_session_ttl_seconds())

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
        path = self.path.split("?", 1)[0]
        if path == "/api/conversations" or path.startswith("/api/conversations/"):
            self._handle_conversations_get(path)
            return
        if path == "/api/auth/session":
            session = self._current_session()
            if session is None:
                self._send_auth_required()
                return
            self._send_json(
                {
                    "status": "authenticated",
                    "user": session.safe_user,
                    "expires_at": session.expires_at.isoformat(),
                },
                headers={"Cache-Control": "no-store"},
            )
            return
        if path in {"/", "/index.html"}:
            self._send_static(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
            return
        if path == "/styles.css":
            self._send_static(STATIC_ROOT / "styles.css", "text/css; charset=utf-8")
            return
        if path == "/professional.css":
            self._send_static(STATIC_ROOT / "professional.css", "text/css; charset=utf-8")
            return
        if path == "/app.js":
            self._send_static(STATIC_ROOT / "app.js", "application/javascript; charset=utf-8")
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        self._send_json({"status": "error", "message": "Not found."}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API.
        path = self.path.split("?", 1)[0]
        if path == "/api/auth/login":
            self._handle_login()
            return
        if path == "/api/auth/logout":
            self._handle_logout()
            return
        if path == "/api/conversations":
            self._handle_conversation_create()
            return
        if path == "/api/feedback":
            self._handle_feedback()
            return
        if path == "/api/chat":
            self._handle_chat()
            return
        self._send_json({"status": "error", "message": "Not found."}, HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:  # noqa: N802 - stdlib handler API.
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/conversations/"):
            self._handle_conversation_delete(path)
            return
        self._send_json({"status": "error", "message": "Not found."}, HTTPStatus.NOT_FOUND)

    def _handle_login(self) -> None:
        try:
            body = self._read_json()
        except (json.JSONDecodeError, ValueError):
            self._send_json(
                {
                    "status": "error",
                    "reason_code": "INVALID_CREDENTIALS",
                    "message": "Username or password is incorrect.",
                },
                HTTPStatus.UNAUTHORIZED,
            )
            return

        username = body.get("username")
        password = body.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            self._send_invalid_credentials()
            return
        result = self.auth_service.login(username, password)
        if not result.authenticated or result.session is None:
            self._send_invalid_credentials()
            return

        session = result.session
        self._send_json(
            {
                "status": "authenticated",
                "user": session.safe_user,
                "expires_at": session.expires_at.isoformat(),
            },
            headers={
                "Cache-Control": "no-store",
                "Set-Cookie": self._session_cookie(session.session_token, session.expires_at),
            },
        )

    def _handle_logout(self) -> None:
        self.auth_service.logout(self._session_token())
        self._send_json(
            {"status": "signed_out"},
            headers={
                "Cache-Control": "no-store",
                "Set-Cookie": self._clear_session_cookie(),
            },
        )

    def _handle_conversations_get(self, path: str) -> None:
        session = self._current_session()
        if session is None:
            self._send_auth_required()
            return
        try:
            if path == "/api/conversations":
                payload = {
                    "status": "ok",
                    "conversations": self._chat_service().list_authenticated_conversations(session),
                }
            else:
                conversation_id = path[len("/api/conversations/") :]
                payload = self._chat_service().get_authenticated_conversation(session, conversation_id)
                payload["status"] = "ok"
            self._send_json(payload, headers={"Cache-Control": "no-store"})
        except ConversationMemoryError as error:
            self._send_memory_error(error)
        except Exception:
            self._send_json(
                {"status": "error", "reason_code": "CONVERSATION_STORE_ERROR", "message": "Conversation history is temporarily unavailable."},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )

    def _handle_conversation_create(self) -> None:
        session = self._current_session()
        if session is None:
            self._send_auth_required()
            return
        try:
            conversation = self._chat_service().create_authenticated_conversation(session)
            conversation["status"] = "created"
            self._send_json(conversation, headers={"Cache-Control": "no-store"})
        except Exception:
            self._send_json(
                {"status": "error", "reason_code": "CONVERSATION_STORE_ERROR", "message": "We could not start a conversation."},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )

    def _handle_conversation_delete(self, path: str) -> None:
        session = self._current_session()
        if session is None:
            self._send_auth_required()
            return
        conversation_id = path[len("/api/conversations/") :]
        try:
            self._chat_service().delete_authenticated_conversation(session, conversation_id)
            self._send_json({"status": "deleted", "conversation_id": conversation_id})
        except ConversationMemoryError as error:
            self._send_memory_error(error)
        except Exception:
            self._send_json(
                {"status": "error", "reason_code": "CONVERSATION_STORE_ERROR", "message": "We could not delete that conversation."},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )

    def _handle_chat(self) -> None:
        session = self._current_session()
        if session is None:
            self._send_auth_required()
            return
        try:
            body = self._read_json()
        except (json.JSONDecodeError, ValueError):
            self._send_json({"status": "error", "message": "Invalid JSON payload."}, HTTPStatus.BAD_REQUEST)
            return
        if not self._body_identity_matches_session(body, session):
            self._send_identity_mismatch()
            return

        if self._wants_event_stream():
            self._handle_chat_stream(session, body)
            return

        chat_kwargs = _chat_request_kwargs(body)
        try:
            response = _call_compatible(
                self._chat_service().handle_authenticated_message,
                session,
                chat_kwargs,
            )
            self._send_json(response)
        except ConversationMemoryError as error:
            self._send_memory_error(error)
        except Exception:
            self._send_json(
                {"status": "error", "reason_code": "CHAT_SERVICE_ERROR", "message": "We could not complete that request. Try again in a moment."},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )

    def _handle_chat_stream(self, session: AuthenticatedSession, body: Mapping[str, Any]) -> None:
        """Write a bounded SSE contract while preserving the JSON chat path."""

        try:
            self._send_stream_headers()
            started = False
            stream_kwargs = _chat_request_kwargs(body)
            events = _call_compatible(
                self._chat_service().stream_authenticated_message,
                session,
                stream_kwargs,
            )
            for event in events:
                if not isinstance(event, Mapping):
                    continue
                if not started:
                    if event.get("type") != "response.start":
                        self._send_stream_event(
                            {
                                "type": "response.start",
                                "conversation_id": _optional_string(body.get("conversation_id")) or "web-chat",
                                "turn_id": _optional_string(body.get("turn_id")) or "web-turn",
                            }
                        )
                    started = True
                self._send_stream_event(event)
        except _ClientDisconnected:
            # Stopping iteration here also closes an in-flight LangGraph/model
            # stream as far as the synchronous stdlib adapter can observe it.
            return
        except Exception:
            try:
                self._send_stream_event(
                    {
                        "type": "response.error",
                        "reason_code": "STREAM_ERROR",
                        "message": "We could not complete that request. Try again in a moment.",
                        "recoverable": False,
                    }
                )
            except _ClientDisconnected:
                return

    def _wants_event_stream(self) -> bool:
        accepted = self.headers.get("Accept", "")
        return "text/event-stream" in accepted.lower()

    def _send_stream_headers(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", STREAM_CONTENT_TYPE)
        self.send_header("Cache-Control", "no-cache, no-store")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.wfile.flush()

    def _send_stream_event(self, event: Mapping[str, Any]) -> None:
        event_type = event.get("type")
        if not isinstance(event_type, str):
            raise ValueError("stream event is missing its type")
        payload = {key: value for key, value in event.items() if key != "type"}
        try:
            self.wfile.write(encode_sse_event(event_type, payload))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError) as error:
            raise _ClientDisconnected from error

    def _handle_feedback(self) -> None:
        session = self._current_session()
        if session is None:
            self._send_auth_required()
            return
        try:
            body = self._read_json()
        except (json.JSONDecodeError, ValueError):
            self._send_json({"status": "error", "message": "Invalid JSON payload."}, HTTPStatus.BAD_REQUEST)
            return
        if not self._body_identity_matches_session(body, session):
            self._send_identity_mismatch()
            return

        response = self._chat_service().submit_authenticated_feedback(
            session,
            conversation_id=_optional_string(body.get("conversation_id")) or "web-chat",
            turn_id=_optional_string(body.get("turn_id")) or "web-turn",
            rating=str(body.get("rating", "")),
            comment=_optional_string(body.get("comment")),
        )
        status = HTTPStatus.OK if response.get("status") == "stored" else HTTPStatus.BAD_REQUEST
        self._send_json(response, status)

    @classmethod
    def _chat_service(cls) -> Any:
        if cls.service is None:
            from app.services.chat_service import ChatService

            cls.service = ChatService()
        return cls.service

    def _current_session(self) -> AuthenticatedSession | None:
        return self.auth_service.current_session(self._session_token())

    def _session_token(self) -> str | None:
        raw_cookie = self.headers.get("Cookie")
        if not raw_cookie:
            return None
        cookies = SimpleCookie()
        try:
            cookies.load(raw_cookie)
        except (CookieError, ValueError):
            return None
        morsel = cookies.get(SESSION_COOKIE_NAME)
        return morsel.value if morsel is not None else None

    @staticmethod
    def _body_identity_matches_session(body: Mapping[str, Any], session: AuthenticatedSession) -> bool:
        """Treat body user_id as an optional consistency check, never authority."""

        if "user_id" not in body:
            return True
        return body.get("user_id") == session.user_id

    def _send_memory_error(self, error: ConversationMemoryError) -> None:
        if isinstance(error, InvalidConversationId):
            status = HTTPStatus.BAD_REQUEST
            reason = "MALFORMED_CONVERSATION_ID"
            message = "The conversation identifier is malformed."
        elif isinstance(error, InvalidTurnId):
            status = HTTPStatus.BAD_REQUEST
            reason = "MALFORMED_TURN_ID"
            message = "The turn identifier is malformed."
        elif isinstance(error, ConversationNotFound):
            status = HTTPStatus.NOT_FOUND
            reason = "CONVERSATION_NOT_FOUND"
            message = "That conversation is not available."
        elif isinstance(error, IdempotencyConflict):
            status = HTTPStatus.CONFLICT
            reason = "TURN_ID_REUSE"
            message = "That turn identifier is already associated with another request."
        elif isinstance(error, TurnInProgress):
            status = HTTPStatus.CONFLICT
            reason = "TURN_IN_PROGRESS"
            message = "That turn is already being processed."
        else:
            status = HTTPStatus.SERVICE_UNAVAILABLE
            reason = "CONVERSATION_STORE_ERROR"
            message = "Conversation history is temporarily unavailable."
        self._send_json({"status": "error", "reason_code": reason, "message": message}, status)

    def _send_auth_required(self) -> None:
        self._send_json(
            {
                "status": "error",
                "reason_code": "AUTHENTICATION_REQUIRED",
                "message": "Sign in before using this endpoint.",
            },
            HTTPStatus.UNAUTHORIZED,
            headers={"Cache-Control": "no-store"},
        )

    def _send_invalid_credentials(self) -> None:
        self._send_json(
            {
                "status": "error",
                "reason_code": "INVALID_CREDENTIALS",
                "message": "Username or password is incorrect.",
            },
            HTTPStatus.UNAUTHORIZED,
            headers={"Cache-Control": "no-store"},
        )

    def _send_identity_mismatch(self) -> None:
        self._send_json(
            {
                "status": "error",
                "reason_code": "IDENTITY_MISMATCH",
                "message": "The request identity must match the authenticated session.",
            },
            HTTPStatus.FORBIDDEN,
        )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature.
        # Do not write request bodies, cookies, usernames, or password material
        # to development logs.  The local server intentionally has no access log.
        return

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("invalid content length") from error
        if length < 0 or length > 1_000_000:
            raise ValueError("request body too large")
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    def _send_json(
        self,
        payload: dict[str, Any],
        status: HTTPStatus = HTTPStatus.OK,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        raw = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def _send_static(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self._send_json({"status": "error", "message": "Static asset missing."}, HTTPStatus.NOT_FOUND)
            return
        raw = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    @staticmethod
    def _session_cookie(token: str, expires_at: datetime) -> str:
        secure = "; Secure" if _env_bool("NEXUSONE_AUTH_COOKIE_SECURE", False) else ""
        max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
        return (
            f"{SESSION_COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax{secure}"
        )

    @staticmethod
    def _clear_session_cookie() -> str:
        secure = "; Secure" if _env_bool("NEXUSONE_AUTH_COOKIE_SECURE", False) else ""
        return f"{SESSION_COOKIE_NAME}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax{secure}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the NexusOne local development web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def _chat_request_kwargs(body: Mapping[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "message": body.get("message") if isinstance(body.get("message"), str) else "",
        "include_trace": _as_bool(body.get("include_trace", False)),
        "memory_opt_in": _as_bool(body.get("memory_opt_in", False)),
    }
    if "conversation_id" in body and body.get("conversation_id") is not None:
        kwargs["conversation_id"] = body.get("conversation_id")
    if "turn_id" in body and body.get("turn_id") is not None:
        kwargs["turn_id"] = body.get("turn_id")
    conversation_context = _safe_conversation_context(body.get("conversation_context"))
    active_ticket_draft = _safe_ticket_draft(body.get("active_ticket_draft"))
    if conversation_context:
        kwargs["conversation_context"] = conversation_context
    if active_ticket_draft:
        kwargs["active_ticket_draft"] = active_ticket_draft
    return kwargs


def _call_compatible(method: Any, session: AuthenticatedSession, kwargs: Mapping[str, Any]) -> Any:
    """Keep old injected test doubles/source-compatible adapters working."""

    try:
        parameters = inspect.signature(method).parameters
        accepted = {name for name in parameters if name != "self"}
        filtered = {key: value for key, value in kwargs.items() if key in accepted}
    except (TypeError, ValueError):
        filtered = dict(kwargs)
    return method(session, **filtered)


def _safe_conversation_context(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, Mapping):
        return {}
    recent = value.get("recent_user_messages")
    if not isinstance(recent, list | tuple):
        return {}
    return {
        "recent_user_messages": [item.strip()[:300] for item in recent if isinstance(item, str) and item.strip()][:3]
    }


def _safe_ticket_draft(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        key: item.strip()[:240]
        for key in ("department", "category", "priority", "description")
        if isinstance(item := value.get(key), str) and item.strip()
    }


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    args = build_parser().parse_args()
    server = ThreadingHTTPServer((args.host, args.port), NexusOneRequestHandler)
    print(f"NexusOne local development server running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
