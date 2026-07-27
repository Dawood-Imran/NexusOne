from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
APP_JS = ROOT / "frontend" / "static" / "app.js"
INDEX_HTML = ROOT / "frontend" / "static" / "index.html"


class StaticChatUIContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app_js = APP_JS.read_text(encoding="utf-8")
        self.index_html = INDEX_HTML.read_text(encoding="utf-8")

    def test_combined_responses_render_citations_and_sql_sources(self) -> None:
        self.assertIn("function collectSourceItems(payload)", self.app_js)
        self.assertIn("const citations = Array.isArray(payload.citations) ? payload.citations : [];", self.app_js)
        self.assertIn("const sources = Array.isArray(payload.sources) ? payload.sources : [];", self.app_js)
        self.assertIn("return [...citations, ...sources];", self.app_js)
        self.assertIn("const sourceItems = collectSourceItems(message);", self.app_js)
        self.assertIn("inspectorContent.appendChild(renderSources(sourceItems));", self.app_js)

    def test_inline_citation_buttons_link_to_source_cards(self) -> None:
        self.assertIn("className = \"citation-ref\"", self.app_js)
        self.assertIn("aria-label", self.app_js)
        self.assertIn("document.querySelector(`#source-${referenceId}`)", self.app_js)
        self.assertIn("source.scrollIntoView", self.app_js)

    def test_source_cards_show_permitted_chunk_text(self) -> None:
        self.assertIn("const sourceText = item.text || item.excerpt;", self.app_js)
        self.assertIn("className = \"source-excerpt\"", self.app_js)
        self.assertIn("excerpt.textContent = sourceText;", self.app_js)

    def test_ticket_and_feedback_controls_exist(self) -> None:
        self.assertIn("function renderTicketSummary(ticket)", self.app_js)
        self.assertIn("className = \"ticket-summary\"", self.app_js)
        self.assertIn("function renderFeedbackControls(payload)", self.app_js)
        self.assertIn("function sendFeedback(button, payload, rating)", self.app_js)
        self.assertIn("\"/api/feedback\"", self.app_js)

    def test_auth_and_conversation_workspace_exist(self) -> None:
        self.assertIn("id=\"authView\"", self.index_html)
        self.assertIn("id=\"appView\"", self.index_html)
        self.assertIn("NexusOne Copilot</h1>", self.index_html)
        self.assertIn("class=\"skip-link\"", self.index_html)
        self.assertIn("id=\"profileCards\"", self.index_html)
        self.assertIn("id=\"conversationList\"", self.index_html)
        self.assertIn("id=\"newChatButton\"", self.index_html)
        self.assertIn("id=\"inspector\"", self.index_html)

    def test_profile_scoped_conversation_persistence_exists(self) -> None:
        self.assertIn("const STORAGE_PREFIX = \"nexusone.conversations.\";", self.app_js)
        self.assertIn("const SESSION_KEY = \"nexusone.activeUserId\";", self.app_js)
        self.assertIn("function signIn(userId)", self.app_js)
        self.assertIn("function loadConversations(userId)", self.app_js)
        self.assertIn("function saveConversations()", self.app_js)
        self.assertIn("function startNewChat()", self.app_js)

    def test_trace_control_exists_in_chat_workspace(self) -> None:
        self.assertIn("id=\"traceToggle\"", self.index_html)
        self.assertIn("<span>Trace</span>", self.index_html)

    def test_mobile_inspector_state_is_accessible(self) -> None:
        self.assertIn("aria-expanded=\"false\"", self.index_html)
        self.assertIn("function openInspector()", self.app_js)
        self.assertIn("function closeInspector()", self.app_js)
        self.assertIn("mobileInspectorButton.setAttribute(\"aria-expanded\", \"true\");", self.app_js)
        self.assertIn("mobileInspectorButton.setAttribute(\"aria-expanded\", \"false\");", self.app_js)

    def test_ready_message_does_not_show_feedback_controls(self) -> None:
        self.assertIn("![\"error\", \"ready\"].includes(message.status)", self.app_js)


if __name__ == "__main__":
    unittest.main()
