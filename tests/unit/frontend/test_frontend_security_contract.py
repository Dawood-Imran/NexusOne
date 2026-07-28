from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
APP_JS = ROOT / "frontend" / "static" / "app.js"
INDEX_HTML = ROOT / "frontend" / "static" / "index.html"


class FrontendEventAndSecurityContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app_js = APP_JS.read_text(encoding="utf-8")
        self.index_html = INDEX_HTML.read_text(encoding="utf-8")

    def test_client_does_not_send_role_or_identity_as_chat_authority(self) -> None:
        chat_call = self.app_js.split('fetch("/api/chat"', 1)[1].split("});", 1)[0]
        feedback_call = self.app_js.split('fetch("/api/feedback"', 1)[1].split("});", 1)[0]

        self.assertNotIn("user_id:", chat_call)
        self.assertNotIn("role:", chat_call)
        self.assertNotIn("profile:", chat_call)
        self.assertNotIn("user_id:", feedback_call)
        self.assertIn('credentials: "same-origin"', chat_call)
        self.assertIn('credentials: "same-origin"', feedback_call)

    def test_stream_parser_accepts_only_public_response_event_types(self) -> None:
        parser = self.app_js.split("function parseStreamEvent", 1)[1].split("function", 1)[0]

        self.assertIn("payload.type !== eventName", parser)
        self.assertIn('event.type === "response.start"', self.app_js)
        self.assertIn('event.type === "response.delta"', self.app_js)
        self.assertIn('event.type === "response.error"', self.app_js)
        self.assertIn('event.type === "response.complete"', self.app_js)
        self.assertIn("A response event was malformed; continuing safely.", self.app_js)
        self.assertNotIn("graph_state", self.app_js)

    def test_server_payloads_are_rendered_as_text_or_escaped_html(self) -> None:
        self.assertIn("cell.textContent = displayStructuredValue(column, value);", self.app_js)
        self.assertIn("function escapeHtml(value)", self.app_js)
        self.assertIn("container.textContent = \"\"", self.app_js)
        self.assertIn("document.createTextNode(part)", self.app_js)
        self.assertIn("textContent = account.name", self.app_js)
        self.assertIn('aria-live="polite"', self.index_html)

    def test_auth_and_session_expiry_use_recoverable_ui_states(self) -> None:
        self.assertIn("setAuthenticating(true)", self.app_js)
        self.assertIn("setAuthenticating(false)", self.app_js)
        self.assertIn("handleSessionExpired", self.app_js)
        self.assertIn("Request stopped.", self.app_js)
        self.assertIn("Try again", self.app_js)


if __name__ == "__main__":
    unittest.main()
