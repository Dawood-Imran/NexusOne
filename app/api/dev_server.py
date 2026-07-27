"""Small stdlib HTTP server for local Phase 1 development."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app.services.chat_service import ChatService


ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = ROOT / "frontend" / "static"


class NexusOneRequestHandler(BaseHTTPRequestHandler):
    service = ChatService()

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API.
        if self.path == "/api/profiles":
            self._send_json({"profiles": self.service.profiles()})
            return
        path = self.path.split("?", 1)[0]
        if path in {"/", "/index.html"}:
            self._send_static(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
            return
        if path == "/styles.css":
            self._send_static(STATIC_ROOT / "styles.css", "text/css; charset=utf-8")
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
        if self.path == "/api/feedback":
            self._handle_feedback()
            return
        if self.path != "/api/chat":
            self._send_json({"status": "error", "message": "Not found."}, HTTPStatus.NOT_FOUND)
            return
        try:
            body = self._read_json()
            response = self.service.handle_message(
                user_id=str(body.get("user_id", "")),
                message=str(body.get("message", "")),
                include_trace=bool(body.get("include_trace", False)),
            )
            self._send_json(response)
        except json.JSONDecodeError:
            self._send_json({"status": "error", "message": "Invalid JSON payload."}, HTTPStatus.BAD_REQUEST)

    def _handle_feedback(self) -> None:
        try:
            body = self._read_json()
            response = self.service.submit_feedback(
                conversation_id=_optional_string(body.get("conversation_id")) or "web-chat",
                turn_id=_optional_string(body.get("turn_id")) or "web-turn",
                user_id=_optional_string(body.get("user_id")),
                rating=str(body.get("rating", "")),
                comment=_optional_string(body.get("comment")),
            )
            status = HTTPStatus.OK if response.get("status") == "stored" else HTTPStatus.BAD_REQUEST
            self._send_json(response, status)
        except json.JSONDecodeError:
            self._send_json({"status": "error", "message": "Invalid JSON payload."}, HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - stdlib signature.
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        raw = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the NexusOne Phase 1 dev web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def main() -> int:
    args = build_parser().parse_args()
    server = ThreadingHTTPServer((args.host, args.port), NexusOneRequestHandler)
    print(f"NexusOne dev server running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
