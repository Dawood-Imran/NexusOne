from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
APP_JS = ROOT / "frontend" / "static" / "app.js"
INDEX_HTML = ROOT / "frontend" / "static" / "index.html"
STYLES_CSS = ROOT / "frontend" / "static" / "styles.css"


class StaticChatUIContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app_js = APP_JS.read_text(encoding="utf-8")
        self.index_html = INDEX_HTML.read_text(encoding="utf-8")
        self.styles = STYLES_CSS.read_text(encoding="utf-8")

    def test_login_uses_username_password_auth_contract(self) -> None:
        self.assertIn('id="loginForm"', self.index_html)
        self.assertIn('id="usernameInput"', self.index_html)
        self.assertIn('autocomplete="username"', self.index_html)
        self.assertIn('id="passwordInput"', self.index_html)
        self.assertIn('autocomplete="current-password"', self.index_html)
        self.assertIn('id="loginButton"', self.index_html)
        self.assertIn('const AUTH_ENDPOINTS = {', self.app_js)
        self.assertIn('login: "/api/auth/login"', self.app_js)
        self.assertIn('session: "/api/auth/session"', self.app_js)
        self.assertIn('logout: "/api/auth/logout"', self.app_js)
        self.assertIn('body: JSON.stringify({ username, password })', self.app_js)
        self.assertIn("Those credentials were not accepted.", self.app_js)

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

    def test_auth_loading_backend_error_and_session_expiry_states_exist(self) -> None:
        self.assertIn("setAuthenticating(true)", self.app_js)
        self.assertIn('setAuthServiceState("Sign-in service unavailable", "error")', self.app_js)
        self.assertIn("authServiceError(response.status)", self.app_js)
        self.assertIn("async function handleSessionExpired()", self.app_js)
        self.assertIn("Your session expired. Sign in again to continue your conversation.", self.app_js)
        self.assertIn("async function logout()", self.app_js)
        self.assertIn('id="logoutButton"', self.index_html)

    def test_no_demo_profile_picker_or_role_switcher_after_login(self) -> None:
        self.assertNotIn('id="profileCards"', self.index_html)
        self.assertNotIn('id="profileSelect"', self.index_html)
        self.assertNotIn("Choose your workspace profile", self.index_html)
        self.assertNotIn("/api/profiles", self.app_js)
        self.assertNotIn("STORAGE_PREFIX + \"activeUserId\"", self.app_js)
        self.assertIn("function enterWorkspace(account, sessionToken = null)", self.app_js)
        self.assertIn("state.account = account", self.app_js)
        self.assertIn('body: JSON.stringify({ message: cleanText, include_trace: traceToggle.checked })', self.app_js)
        self.assertNotIn('user_id: state.account.user_id', self.app_js)

    def test_account_control_is_immutable_and_details_are_accessible(self) -> None:
        self.assertIn('id="accountButton"', self.index_html)
        self.assertIn('aria-expanded="false"', self.index_html)
        self.assertIn('aria-controls="accountPopover"', self.index_html)
        self.assertIn('id="accountAvatarImage"', self.index_html)
        self.assertIn('id="accountPopover"', self.index_html)
        self.assertIn('id="accountDetailRole"', self.index_html)
        self.assertIn('id="accountDetailEmail"', self.index_html)
        self.assertIn("function updateAccountControl()", self.app_js)
        self.assertIn("function normalizeAccount(payload)", self.app_js)
        self.assertIn("accountButton.addEventListener(\"focus\", openAccountPopover)", self.app_js)
        self.assertIn("function closeAccountPopover()", self.app_js)
        self.assertIn("event.key === \"Escape\"", self.app_js)
        self.assertNotIn("workspace-identity", self.index_html)
        self.assertNotIn("profile-summary", self.index_html)

    def test_sidebar_keeps_navigation_and_conversation_structure(self) -> None:
        self.assertIn('aria-label="Workspace navigation and conversations"', self.index_html)
        self.assertIn('aria-label="Primary navigation"', self.index_html)
        self.assertIn('id="conversationList"', self.index_html)
        self.assertIn('id="conversationHeading">Conversations', self.index_html)
        self.assertIn('id="newChatButton"', self.index_html)
        self.assertIn('id="conversationEmpty"', self.index_html)
        self.assertIn('id="inspector"', self.index_html)
        self.assertIn("function startNewChat()", self.app_js)
        self.assertIn("function renderConversationList()", self.app_js)

    def test_citations_sources_ticket_feedback_and_trace_are_preserved(self) -> None:
        self.assertIn("function collectSourceItems(payload)", self.app_js)
        self.assertIn("return [...citations, ...sources];", self.app_js)
        self.assertIn("function renderSourceCard(item)", self.app_js)
        self.assertIn('className = "citation-ref"', self.app_js)
        self.assertIn("source.scrollIntoView", self.app_js)
        self.assertIn("function renderTicketSummary(ticket)", self.app_js)
        self.assertIn("function renderFeedbackControls(payload)", self.app_js)
        self.assertIn('fetch("/api/feedback"', self.app_js)
        self.assertIn("function renderTrace(trace, subgraphTrace = [])", self.app_js)
        self.assertIn("function renderDeniedNextStep(payload)", self.app_js)
        self.assertIn("function renderRetry(text)", self.app_js)

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
        self.assertIn('aria-label="NexusOne Copilot workspace"', self.index_html)
        self.assertIn('aria-labelledby="pageTitle"', self.index_html)
        self.assertIn('aria-live="polite"', self.index_html)
        self.assertIn('id="accountButton"', self.index_html)
        self.assertNotIn('id="profileSelect"', self.index_html)

    def test_composer_auto_resizes_and_keeps_send_action_usable(self) -> None:
        self.assertIn('id="messageInput"', self.index_html)
        self.assertIn('maxlength="2000"', self.index_html)
        self.assertIn('id="sendButton"', self.index_html)
        self.assertIn("const MAX_COMPOSER_HEIGHT = 168", self.app_js)
        self.assertIn("function autoResizeComposer()", self.app_js)
        self.assertIn('messageInput.style.height = "auto"', self.app_js)
        self.assertIn("messageInput.scrollHeight", self.app_js)
        self.assertIn("autoResizeComposer();", self.app_js)
        self.assertIn("messageInput.addEventListener(\"input\"", self.app_js)
        self.assertIn("grid-template-columns: minmax(0, 1fr) 94px", self.styles)
        self.assertIn("align-self: end", self.styles)
        self.assertIn("resize: none", self.styles)

    def test_suggestions_fill_composer_without_mocking_chat(self) -> None:
        self.assertIn('id="suggestions"', self.index_html)
        self.assertIn('data-prompt="How do I request AWS access?"', self.index_html)
        self.assertIn('data-prompt="Show my ticket status."', self.index_html)
        self.assertIn('button.dataset.prompt || ""', self.app_js)
        self.assertIn("messageInput.focus();", self.app_js)
        self.assertIn('fetch("/api/chat"', self.app_js)

    def test_responsive_accessible_and_reduced_motion_contracts_exist(self) -> None:
        self.assertIn('class="skip-link"', self.index_html)
        self.assertIn('aria-live="polite"', self.index_html)
        self.assertIn('@media (max-width: 760px)', self.styles)
        self.assertIn('@media (max-width: 480px)', self.styles)
        self.assertIn('@media (prefers-reduced-motion: reduce)', self.styles)
        self.assertIn(".inspector.open", self.styles)
        self.assertIn("touch-action: manipulation", self.styles)
        self.assertIn("min-height: 46px", self.styles)
        self.assertIn(".message.denied", self.styles)
        self.assertIn(".message.error", self.styles)

    def test_professional_workspace_visual_system_is_loaded(self) -> None:
        styles = (ROOT / "frontend" / "static" / "professional.css").read_text(encoding="utf-8")
        self.assertIn('href="/professional.css"', self.index_html)
        self.assertIn("Professional enterprise product layer", styles)
        self.assertIn(".message.assistant.selected", styles)
        self.assertIn(".conversation-status::before", styles)
        self.assertIn("grid-template-columns: minmax(0, 1.08fr) minmax(390px, 0.92fr)", styles)
        self.assertIn(".profile-cards .profile-card:hover", styles)
        self.assertIn(".skip-link:focus", styles)
        self.assertIn("formatRole(profile.role)", self.app_js)
        self.assertIn("@media (max-width: 1400px)", styles)
        self.assertIn(".inspector.open", styles)


if __name__ == "__main__":
    unittest.main()
