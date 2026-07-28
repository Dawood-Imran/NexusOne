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

    def test_streaming_chat_uses_explicit_sse_events_and_progressive_message_state(self) -> None:
        self.assertIn('Accept: "text/event-stream"', self.app_js)
        self.assertIn("async function consumeStream(response, onEvent)", self.app_js)
        self.assertIn("function parseStreamEvent(frame)", self.app_js)
        self.assertIn('event.type === "response.delta"', self.app_js)
        self.assertIn('event.type === "response.complete"', self.app_js)
        self.assertIn('event.type === "response.error"', self.app_js)
        self.assertIn("function beginStreamingAssistantMessage()", self.app_js)
        self.assertIn("function updateStreamingAssistantMessage(delta)", self.app_js)
        self.assertIn("function finalizeStreamingAssistantMessage(payload)", self.app_js)
        self.assertIn("message.message += String(delta)", self.app_js)
        self.assertIn("message.message = payload.message || message.message ||", self.app_js)
        self.assertIn('status: "streaming"', self.app_js)
        self.assertIn('message.status !== "streaming"', self.app_js)

    def test_streaming_handles_malformed_frames_and_client_abort_without_stuck_loading(self) -> None:
        self.assertIn("A response event was malformed; continuing safely.", self.app_js)
        self.assertIn("new AbortController()", self.app_js)
        self.assertIn("signal: controller.signal", self.app_js)
        self.assertIn('error?.name === "AbortError"', self.app_js)
        self.assertIn("function removeStreamingAssistantMessage()", self.app_js)
        self.assertIn('setConversationStatus("Request stopped.")', self.app_js)
        self.assertIn("reader.releaseLock()", self.app_js)
        self.assertIn('window.addEventListener("pagehide"', self.app_js)

    def test_live_structured_rows_have_a_safe_inspector_table(self) -> None:
        self.assertIn("rows: Array.isArray(payload.rows) ? payload.rows : [],", self.app_js)
        self.assertIn("function renderStructuredRows(message)", self.app_js)
        self.assertIn("cell.textContent = String(value);", self.app_js)
        self.assertIn("Structured data", self.app_js)

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

    def test_sidebar_keeps_conversation_structure_without_workspace_action(self) -> None:
        self.assertIn('aria-label="Workspace navigation and conversations"', self.index_html)
        self.assertNotIn('aria-label="Primary navigation"', self.index_html)
        self.assertNotIn('class="workspace-nav"', self.index_html)
        self.assertNotIn('>Workspace<', self.index_html)
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
        self.assertIn("function renderTrace(trace, subgraphTrace = [], expanded = true, onToggle = null)", self.app_js)
        self.assertIn("function renderDeniedNextStep(payload)", self.app_js)
        self.assertIn("function renderRetry(text, titleText = \"Connection issue\")", self.app_js)

    def test_route_metadata_is_safe_and_visible_for_new_routes(self) -> None:
        self.assertIn("route: payload.route || null,", self.app_js)
        self.assertIn('<div><dt>Route</dt><dd>${escapeHtml(message.route || "-")}</dd></div>', self.app_js)

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
        self.assertIn("mobileInspectorButton.focus();", self.app_js)

    def test_normal_and_no_answer_messages_have_no_ready_or_match_status_label(self) -> None:
        self.assertIn("![\"error\", \"refused\", \"ready\"].includes(message.status)", self.app_js)
        self.assertNotIn('answered: "Ready"', self.app_js)
        self.assertNotIn('no_answer: "No match"', self.app_js)
        self.assertNotIn("No match", self.index_html)
        self.assertNotIn("Ready when", self.index_html)
        self.assertIn('setConversationStatus("");', self.app_js)

    def test_requested_shell_copy_and_provider_diagnostics_are_not_user_facing(self) -> None:
        self.assertNotIn(">Ask Copilot<", self.index_html)
        self.assertNotIn(">Live<", self.index_html)
        self.assertNotIn("Answer ready. Review the approved sources below it.", self.app_js)
        self.assertNotIn("Enter a question in plain language", self.index_html)
        self.assertNotIn("Waiting for an authenticated session", self.index_html)
        self.assertNotIn("configured_with_fallback", self.index_html)
        self.assertNotIn("configured_with_fallback", self.app_js)
        self.assertNotIn("SQL capability", self.app_js)
        self.assertNotIn("Access checked", self.index_html)
        self.assertNotIn("Access checked", self.app_js)
        self.assertNotIn("Protected session", self.index_html)
        self.assertNotIn("Protected session", self.app_js)
        self.assertNotIn("Session ready", self.index_html)
        self.assertNotIn("Session ready", self.app_js)

    def test_ticket_cards_are_structured_and_error_states_are_concise(self) -> None:
        self.assertIn("function sanitizeTicket(ticket)", self.app_js)
        self.assertIn('function safeTicketStatus(value)', self.app_js)
        self.assertIn('function renderTicketStatusState()', self.app_js)
        self.assertIn('status.textContent = "Status unavailable"', self.app_js)
        self.assertIn('ticket: sanitizeTicket(payload.ticket)', self.app_js)
        self.assertNotIn("ticket.message", self.app_js)
        self.assertNotIn("ticket.error", self.app_js)

    def test_trace_is_only_rendered_in_the_inspector_for_historical_turn_selection(self) -> None:
        message_renderer = self.app_js.split("function selectAssistantMessage", 1)[0]
        self.assertNotIn("article.appendChild(renderTrace", message_renderer)
        self.assertIn("inspectorContent.appendChild(renderTrace(message.trace || [], message.subgraph_trace || []", self.app_js)
        self.assertIn("state.selectedAssistantMessageId = latestAssistantMessage(conversation)?.id || null", self.app_js)
        self.assertIn("function selectAssistantMessage(messageId)", self.app_js)

    def test_each_answer_owns_a_reopenable_trace_and_new_questions_collapse_previous(self) -> None:
        self.assertIn("trace_expanded: Boolean(payload.trace?.length || payload.subgraph_trace?.length)", self.app_js)
        self.assertIn("message.trace_expanded = false", self.app_js)
        self.assertIn('summary.textContent = "Trace for this answer"', self.app_js)
        self.assertIn('section.className = "trace"', self.app_js)
        self.assertIn('section.addEventListener("toggle", () => onToggle(section.open))', self.app_js)
        self.assertNotIn("setSidebarExpanded", self.app_js)
        self.assertNotIn("leftSidebarToggle", self.app_js)
        self.assertNotIn('id="leftSidebarToggle"', self.index_html)
        self.assertIn('aria-controls="inspector"', self.index_html)

    def test_shell_has_accessible_profile_context_and_composer_states(self) -> None:
        self.assertIn('aria-label="NexusOne Copilot workspace"', self.index_html)
        self.assertIn('aria-labelledby="pageTitle"', self.index_html)
        self.assertIn('aria-live="polite"', self.index_html)
        self.assertIn('id="accountButton"', self.index_html)
        self.assertNotIn('id="profileSelect"', self.index_html)

    def test_composer_auto_resizes_and_keeps_send_action_usable(self) -> None:
        self.assertIn('id="messageInput"', self.index_html)
        self.assertIn('maxlength="2000"', self.index_html)
        self.assertNotIn('id="characterCount"', self.index_html)
        self.assertNotIn("characterCount", self.app_js)
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

    def test_enter_submits_and_shift_enter_keeps_multiline_composer(self) -> None:
        keydown = self.app_js.split('messageInput.addEventListener("keydown"', 1)[1].split('suggestions.addEventListener', 1)[0]
        self.assertIn('event.key === "Enter"', keydown)
        self.assertIn("!event.shiftKey", keydown)
        self.assertIn("event.preventDefault()", keydown)
        self.assertIn("chatForm.requestSubmit()", keydown)
        self.assertNotIn("if (event.shiftKey)", keydown)
        self.assertIn('rows="1"', self.index_html)
        self.assertIn("white-space: pre-wrap", self.styles)

    def test_delete_conversation_confirms_and_rehomes_the_active_view(self) -> None:
        self.assertIn("function deleteConversation(conversationId)", self.app_js)
        self.assertIn("window.confirm(`Delete “${conversation.title}”?", self.app_js)
        self.assertIn("state.conversations = state.conversations.filter((candidate) => candidate.id !== conversationId)", self.app_js)
        self.assertIn("renderConversationList();\n  renderActiveConversation();", self.app_js)
        self.assertIn('className = "delete-conversation-button"', self.app_js)
        self.assertIn('aria-label", `Delete conversation ${conversation.title}`', self.app_js)
        self.assertIn("saveConversations();", self.app_js)

    def test_remaining_right_control_is_a_centered_chevron_with_accessible_labels(self) -> None:
        self.assertNotIn('title="Collapse navigation"', self.index_html)
        self.assertNotIn('class="sidebar-toggle-label sr-only"', self.index_html)
        self.assertIn('title="Show conversation details"', self.index_html)
        self.assertIn('title="Collapse conversation details"', self.index_html)
        self.assertIn('function setIconControlLabel(control, label)', self.app_js)
        self.assertIn("control.title = label", self.app_js)
        self.assertIn('mobileInspectorButton.querySelector(".panel-toggle-icon").textContent = ">"', self.app_js)
        self.assertIn('closeInspectorButton.querySelector(".panel-toggle-icon").textContent = ">"', self.app_js)
        self.assertNotIn('textContent = "×"', self.app_js)
        self.assertIn('place-items: center', self.styles)
        self.assertIn('text-align: center', self.styles)

    def test_suggestions_fill_composer_without_mocking_chat(self) -> None:
        self.assertIn('id="suggestions"', self.index_html)
        self.assertIn('data-prompt="How do I request AWS access?"', self.index_html)
        self.assertIn('data-prompt="Show my ticket status."', self.index_html)
        self.assertIn('button.dataset.prompt || ""', self.app_js)
        self.assertIn("function updateSuggestionsVisibility()", self.app_js)
        self.assertIn("suggestions.hidden = hasSubmittedResponse", self.app_js)
        self.assertIn("message.role === \"assistant\"", self.app_js)
        self.assertIn("messageInput.focus();", self.app_js)
        self.assertIn('fetch("/api/chat"', self.app_js)

    def test_responsive_accessible_and_reduced_motion_contracts_exist(self) -> None:
        self.assertIn('class="skip-link"', self.index_html)
        self.assertIn('aria-live="polite"', self.index_html)
        self.assertIn('@media (max-width: 760px)', self.styles)
        self.assertIn('@media (max-width: 480px)', self.styles)
        self.assertIn('@media (prefers-reduced-motion: reduce)', self.styles)
        self.assertIn(".inspector.open", self.styles)
        self.assertNotIn(".conversation-rail.is-collapsed", (ROOT / "frontend" / "static" / "professional.css").read_text(encoding="utf-8"))
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
        self.assertIn("formatRole(account.role)", self.app_js)
        self.assertIn("@media (max-width: 1400px)", styles)
        self.assertIn(".inspector.open", styles)

    def test_reference_auth_card_is_centered_without_overriding_form_components(self) -> None:
        styles = (ROOT / "frontend" / "static" / "styles.css").read_text(encoding="utf-8")
        self.assertIn(".auth-frame", styles)
        self.assertIn("width: min(1120px, 100%)", styles)
        self.assertIn(".proof-mark", styles)
        self.assertIn("margin: auto;", styles)
        self.assertIn('id="loginForm"', self.index_html)
        self.assertNotIn('id="profileSelect"', self.index_html)


if __name__ == "__main__":
    unittest.main()
