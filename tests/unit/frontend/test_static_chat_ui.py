from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
APP_JS = ROOT / "frontend" / "static" / "app.js"
INDEX_HTML = ROOT / "frontend" / "static" / "index.html"


class StaticChatUIContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app_js = APP_JS.read_text(encoding="utf-8")
        self.index_html = INDEX_HTML.read_text(encoding="utf-8")

    def test_live_structured_rows_have_a_safe_inspector_table(self) -> None:
        self.assertIn("rows: Array.isArray(payload.rows) ? payload.rows : [],", self.app_js)
        self.assertIn("function renderStructuredRows(message)", self.app_js)
        self.assertIn("cell.textContent = String(value);", self.app_js)
        self.assertIn("Live structured data", self.app_js)

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

    def test_trace_inspector_distinguishes_graph_and_sql_subgraph(self) -> None:
        self.assertIn("subgraph_trace: payload.subgraph_trace || [],", self.app_js)
        self.assertIn('subgraphTitle.textContent = "SQL subgraph trace";', self.app_js)
        self.assertIn("item.status || details.status", self.app_js)

    def test_mobile_inspector_state_is_accessible(self) -> None:
        self.assertIn("aria-expanded=\"false\"", self.index_html)
        self.assertIn("function openInspector()", self.app_js)
        self.assertIn("function closeInspector()", self.app_js)
        self.assertIn("mobileInspectorButton.setAttribute(\"aria-expanded\", \"true\");", self.app_js)
        self.assertIn("mobileInspectorButton.setAttribute(\"aria-expanded\", \"false\");", self.app_js)

    def test_ready_message_does_not_show_feedback_controls(self) -> None:
        self.assertIn("![\"error\", \"ready\"].includes(message.status)", self.app_js)

    def test_shell_has_accessible_profile_context_and_composer_states(self) -> None:
        self.assertIn('aria-label="Workspace context"', self.index_html)
        self.assertIn('aria-labelledby="pageTitle"', self.index_html)
        self.assertIn('aria-live="polite"', self.index_html)
        self.assertIn('id="profileSelect"', self.index_html)
        self.assertIn('id="messageInput"', self.index_html)
        self.assertIn('maxlength="2000"', self.index_html)
        self.assertIn('id="characterCount"', self.index_html)
        self.assertIn('id="emptyState"', self.index_html)

    def test_frontend_covers_loading_error_denied_and_retry_states(self) -> None:
        self.assertIn('id = "loadingMessage"', self.app_js)
        self.assertIn('statusClass = payload.status === "denied"', self.app_js)
        self.assertIn('status === "error"', self.app_js)
        self.assertIn('status === "no_answer"', self.app_js)
        self.assertIn('function renderRetry(text)', self.app_js)
        self.assertIn('The local service did not respond.', self.app_js)

    def test_chat_request_uses_selected_profile_and_trace_setting(self) -> None:
        self.assertIn('user_id: state.activeUserId', self.app_js)
        self.assertIn('include_trace: traceToggle.checked', self.app_js)
        self.assertIn('state.activeUserId = event.target.value;', self.app_js)
        self.assertIn('resetConversation();', self.app_js)

    def test_styles_include_narrow_viewport_and_reduced_motion_support(self) -> None:
        styles = (ROOT / "frontend" / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn("@media (max-width: 760px)", styles)
        self.assertIn("@media (max-width: 430px)", styles)
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertIn(".message.denied", styles)
        self.assertIn(".message.error", styles)


if __name__ == "__main__":
    unittest.main()
