const AUTH_ENDPOINTS = {
  session: "/api/auth/session",
  login: "/api/auth/login",
  logout: "/api/auth/logout",
};
const MAX_COMPOSER_HEIGHT = 168;
const DISPLAY_TIME_ZONE = "UTC";

const state = {
  account: null,
  sessionToken: null,
  conversations: [],
  activeConversationId: null,
  selectedAssistantMessageId: null,
  sending: false,
  authenticating: false,
  lastSubmittedText: "",
  activeStreamController: null,
  streamingMessageId: null,
  sessionExpiredHandled: false,
};

const authView = document.querySelector("#authView");
const appView = document.querySelector("#appView");
const loginForm = document.querySelector("#loginForm");
const usernameInput = document.querySelector("#usernameInput");
const passwordInput = document.querySelector("#passwordInput");
const loginButton = document.querySelector("#loginButton");
const loginButtonLabel = document.querySelector(".login-button-label");
const loginButtonLoader = document.querySelector(".login-button-loader");
const authError = document.querySelector("#authError");
const authStatus = document.querySelector("#authStatus");
const authServiceStatus = document.querySelector("#authServiceStatus");
const authServiceIndicator = document.querySelector("#authServiceIndicator");
const accountButton = document.querySelector("#accountButton");
const accountPopover = document.querySelector("#accountPopover");
const logoutButton = document.querySelector("#logoutButton");
const accountName = document.querySelector("#accountName");
const accountRole = document.querySelector("#accountRole");
const accountAvatarImage = document.querySelector("#accountAvatarImage");
const accountAvatarFallback = document.querySelector("#accountAvatarFallback");
const popoverAvatarImage = document.querySelector("#popoverAvatarImage");
const popoverAvatarFallback = document.querySelector("#popoverAvatarFallback");
const popoverAccountName = document.querySelector("#popoverAccountName");
const popoverAccountTitle = document.querySelector("#popoverAccountTitle");
const accountDetailRole = document.querySelector("#accountDetailRole");
const accountDetailDepartment = document.querySelector("#accountDetailDepartment");
const accountDetailLocation = document.querySelector("#accountDetailLocation");
const accountDetailEmail = document.querySelector("#accountDetailEmail");
const newChatButton = document.querySelector("#newChatButton");
const conversationRail = document.querySelector("#conversationRail");
const leftSidebarToggle = document.querySelector("#leftSidebarToggle");
const conversationList = document.querySelector("#conversationList");
const conversationEmpty = document.querySelector("#conversationEmpty");
const conversationTitle = document.querySelector("#conversationTitle");
const pageTitle = document.querySelector("#pageTitle");
const messages = document.querySelector("#messages");
const chatForm = document.querySelector("#chatForm");
const messageInput = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const traceToggle = document.querySelector("#traceToggle");
const conversationStatus = document.querySelector("#conversationStatus");
const suggestions = document.querySelector("#suggestions");
const inspector = document.querySelector("#inspector");
const inspectorContent = document.querySelector("#inspectorContent");
const closeInspectorButton = document.querySelector("#closeInspectorButton");
let skipNextAccountFocus = false;

async function init() {
  setAuthServiceState("Connecting to sign-in service…", "busy");
  setAuthStatus("Checking for an existing session…");
  try {
    const { response, payload } = await authRequest(AUTH_ENDPOINTS.session);
    if (response.status === 401 || response.status === 403) {
      showLogin();
      setAuthStatus("Sign in to continue.");
      setAuthServiceState("Sign-in service ready", "live");
      return;
    }
    if (!response.ok) {
      showLogin();
      setAuthServiceState(authServiceError(response.status), "error");
      setAuthStatus("Sign in to continue, then try again.");
      setAuthError(payloadMessage(payload) || "We could not verify your session. Try signing in again.");
      return;
    }
    const account = normalizeAccount(payload);
    if (!account) {
      showLogin();
      setAuthServiceState("Sign-in service returned an invalid session", "error");
      setAuthStatus("Sign in to continue, then try again.");
      setAuthError("We could not read the account returned by the sign-in service. Contact your administrator.");
      return;
    }
    await enterWorkspace(account, authToken(payload));
  } catch (error) {
    showLogin();
    setAuthServiceState("Sign-in service unavailable", "error");
    setAuthStatus("Sign in to continue when the service is available.");
    setAuthError("We could not reach the sign-in service. Check the server connection, then try again.");
  }
}

async function authRequest(path, options = {}) {
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers: {
      Accept: "application/json",
      ...(path !== AUTH_ENDPOINTS.login ? sessionHeaders() : {}),
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (error) {
    payload = {};
  }
  return { response, payload };
}

async function submitLogin(event) {
  event.preventDefault();
  const username = usernameInput.value.trim();
  const password = passwordInput.value;
  clearAuthMessage();
  if (!username) {
    setAuthError("Enter your username or work email.");
    usernameInput.focus();
    return;
  }
  if (!password) {
    setAuthError("Enter your password.");
    passwordInput.focus();
    return;
  }

  setAuthenticating(true);
  setAuthServiceState("Signing you in…", "busy");
  setAuthStatus("Verifying credentials and account access…");
  try {
    const { response, payload } = await authRequest(AUTH_ENDPOINTS.login, {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    if (response.status === 401 || response.status === 403) {
      setAuthServiceState("Sign-in service ready", "live");
      setAuthStatus("Check your credentials and try again.");
      setAuthError("Those credentials were not accepted. Check your username and password and try again.");
      passwordInput.select();
      return;
    }
    if (!response.ok) {
      setAuthServiceState(authServiceError(response.status), "error");
      setAuthStatus("Sign in again when the service is available.");
      setAuthError(payloadMessage(payload) || "The sign-in service could not complete your request. Try again.");
      return;
    }
    const account = normalizeAccount(payload);
    if (!account) {
      setAuthServiceState("Sign-in service returned an invalid account", "error");
      setAuthStatus("Sign in again or contact your administrator.");
      setAuthError("The sign-in service did not return a usable account. Contact your administrator.");
      return;
    }
    passwordInput.value = "";
    await enterWorkspace(account, authToken(payload));
  } catch (error) {
    setAuthServiceState("Sign-in service unavailable", "error");
    setAuthStatus("Sign in to continue when the service is available.");
    setAuthError("We could not reach the sign-in service. Check the server connection, then try again.");
  } finally {
    setAuthenticating(false);
  }
}

function authToken(payload) {
  return payload?.access_token || payload?.token || payload?.session?.access_token || null;
}

function sessionHeaders() {
  return state.sessionToken ? { Authorization: `Bearer ${state.sessionToken}` } : {};
}

function normalizeAccount(payload) {
  const candidate = payload?.user || payload?.account || payload?.profile || payload?.session?.user || payload;
  if (!candidate || typeof candidate !== "object") return null;
  const userId = candidate.user_id || candidate.id || candidate.sub;
  if (!userId) return null;
  const name = candidate.name || candidate.full_name || candidate.display_name || candidate.username || "NexusOne user";
  return {
    user_id: String(userId),
    name: String(name),
    email: candidate.email || candidate.username || "Account email unavailable",
    role: candidate.role || "authenticated user",
    department: candidate.department || "Not provided",
    title: candidate.title || "NexusOne team member",
    location: candidate.location || "Not provided",
    avatar_url: candidate.avatar_url || candidate.avatar || "",
    status: candidate.status || "active",
  };
}

function enterWorkspace(account, sessionToken = null) {
  return enterWorkspaceAsync(account, sessionToken);
}

async function enterWorkspaceAsync(account, sessionToken = null) {
  state.account = account;
  state.sessionToken = sessionToken;
  state.sessionExpiredHandled = false;
  state.conversations = await loadConversations();
  if (!state.account) return;
  if (!state.conversations.length) {
    const created = await createServerConversation();
    if (!state.account) return;
    if (created) state.conversations.push(created);
  }
  state.activeConversationId = state.conversations[0]?.id || null;
  state.selectedAssistantMessageId = latestAssistantMessage(activeConversation())?.id || null;
  authView.classList.add("hidden");
  appView.classList.remove("hidden");
  updateAccountControl();
  renderConversationList();
  renderActiveConversation();
  setConversationStatus("");
  setSidebarExpanded(true);
  if (window.matchMedia("(min-width: 981px)").matches) openInspector();
  else closeInspector();
  setComposerAvailability();
  autoResizeComposer();
  messageInput.focus();
}

function showLogin() {
  state.activeStreamController?.abort();
  state.activeStreamController = null;
  state.streamingMessageId = null;
  state.account = null;
  state.sessionToken = null;
  state.sending = false;
  appView.classList.add("hidden");
  authView.classList.remove("hidden");
  setAuthenticating(false);
  accountPopover.hidden = true;
  accountButton.setAttribute("aria-expanded", "false");
  setComposerAvailability();
}

async function logout() {
  if (state.authenticating) return;
  logoutButton.disabled = true;
  closeAccountPopover();
  setAuthStatus("Signing you out…");
  let logoutFailed = false;
  try {
    const { response } = await authRequest(AUTH_ENDPOINTS.logout, { method: "POST", body: "{}" });
    logoutFailed = !response.ok && response.status !== 401;
  } catch (error) {
    logoutFailed = true;
  } finally {
    logoutButton.disabled = false;
  }
  state.account = null;
  state.sessionToken = null;
  state.conversations = [];
  state.activeConversationId = null;
  state.selectedAssistantMessageId = null;
  showLogin();
  usernameInput.value = "";
  passwordInput.value = "";
  setAuthServiceState(logoutFailed ? "Sign-in service did not confirm the session change" : "Sign in to continue", logoutFailed ? "error" : "live");
  setAuthStatus(logoutFailed ? "Try signing in again when the service is available." : "Sign in to continue.");
  if (logoutFailed) setAuthError("The server did not confirm the session change. Try again before sharing this device.");
  usernameInput.focus();
}

async function handleSessionExpired() {
  if (state.sessionExpiredHandled) return;
  state.sessionExpiredHandled = true;
  state.account = null;
  state.sessionToken = null;
  state.sending = false;
  showLogin();
  setAuthServiceState("Session expired", "error");
  setAuthError("Your session expired. Sign in again to continue your conversation.");
  usernameInput.focus();
}

function activeAccount() {
  return state.account;
}

function activeConversation() {
  return state.conversations.find((conversation) => conversation.id === state.activeConversationId);
}

function updateAccountControl() {
  const account = activeAccount();
  if (!account) return;
  const accountInitials = initials(account.name);
  accountName.textContent = account.name;
  accountRole.textContent = formatRole(account.role);
  accountButton.setAttribute("aria-label", `Open account details for ${account.name}`);
  popoverAccountName.textContent = account.name;
  popoverAccountTitle.textContent = account.title || "NexusOne team member";
  accountDetailRole.textContent = formatRole(account.role);
  accountDetailDepartment.textContent = account.department || "Not provided";
  accountDetailLocation.textContent = account.location || "Not provided";
  accountDetailEmail.textContent = account.email || "Account email unavailable";
  setAvatar(accountAvatarImage, accountAvatarFallback, account, accountInitials);
  setAvatar(popoverAvatarImage, popoverAvatarFallback, account, accountInitials);
}

function setAvatar(image, fallback, account, accountInitials) {
  image.hidden = true;
  image.removeAttribute("src");
  fallback.hidden = false;
  fallback.textContent = accountInitials || "N1";
  if (!account.avatar_url) return;
  image.src = account.avatar_url;
  image.alt = `${account.name} account avatar`;
  image.hidden = false;
  fallback.hidden = true;
  image.onerror = () => {
    image.hidden = true;
    fallback.hidden = false;
  };
}

function toggleAccountPopover() {
  if (!state.account) return;
  const isOpen = !accountPopover.hidden;
  if (isOpen) closeAccountPopover();
  else openAccountPopover();
}

function openAccountPopover() {
  if (!state.account) return;
  if (skipNextAccountFocus) {
    skipNextAccountFocus = false;
    return;
  }
  accountPopover.hidden = false;
  accountButton.setAttribute("aria-expanded", "true");
}

function closeAccountPopover() {
  accountPopover.hidden = true;
  accountButton.setAttribute("aria-expanded", "false");
}

function createConversationRecord(data = {}) {
  return {
    id: data.conversation_id || data.id || null,
    title: data.title || "New conversation",
    createdAt: data.created_at || data.createdAt || new Date().toISOString(),
    updatedAt: data.updated_at || data.updatedAt || new Date().toISOString(),
    messages: Array.isArray(data.messages) ? data.messages : [],
  };
}

function normalizeServerConversation(data) {
  const conversation = createConversationRecord(data);
  const turns = Array.isArray(data.turns) ? data.turns : [];
  conversation.messages = [];
  turns.forEach((turn) => {
    if (typeof turn?.user_message === "string") {
      conversation.messages.push({ id: `user-${turn.turn_id}`, role: "user", message: turn.user_message });
    }
    if (turn?.response && typeof turn.response === "object") {
      const payload = turn.response;
      conversation.messages.push({
        id: `assistant-${turn.turn_id}`,
        role: "assistant",
        status: payload.status || "answered",
        reason_code: payload.reason_code,
        route: payload.route || null,
        message: payload.message || "No response was returned.",
        citations: Array.isArray(payload.citations) ? payload.citations : [],
        sources: Array.isArray(payload.sources) ? payload.sources : [],
        rows: Array.isArray(payload.rows) ? payload.rows : [],
        columns: Array.isArray(payload.columns) ? payload.columns : [],
        row_count: Number.isInteger(payload.row_count) ? payload.row_count : 0,
        sql_execution: payload.sql_execution || null,
        model_backend: payload.model_backend || null,
        capabilities: payload.capabilities || null,
        category: payload.category || null,
        subgraph_trace: payload.subgraph_trace || [],
        ticket: sanitizeTicket(payload.ticket),
        ticket_preview: sanitizeTicketPreview(payload.ticket_preview),
        approval_required: payload.approval_required === true,
        trace_expanded: false,
        missing_fields: payload.missing_fields || [],
        allowed_alternatives: payload.allowed_alternatives || [],
        trace: payload.trace || [],
        conversation_id: payload.conversation_id || conversation.id,
        turn_id: payload.turn_id || turn.turn_id,
        latency_ms: payload.latency_ms,
        feedback: payload.feedback,
      });
    }
  });
  return conversation;
}

async function loadConversations() {
  try {
    const response = await fetch("/api/conversations", {
      credentials: "same-origin",
      headers: { Accept: "application/json", ...sessionHeaders() },
    });
    if (response.status === 401 || response.status === 403) {
      await handleSessionExpired();
      return [];
    }
    if (!response.ok) throw new Error("conversation history unavailable");
    const payload = await response.json();
    return Array.isArray(payload.conversations) ? payload.conversations.map(normalizeServerConversation) : [];
  } catch (error) {
    setConversationStatus("Your server conversation history is unavailable. Try again when the service is ready.", "error");
    return [];
  }
}

async function createServerConversation() {
  try {
    const response = await fetch("/api/conversations", {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "application/json", "Content-Type": "application/json", ...sessionHeaders() },
      body: "{}",
    });
    if (response.status === 401 || response.status === 403) {
      await handleSessionExpired();
      return null;
    }
    if (!response.ok) throw new Error("conversation create failed");
    return normalizeServerConversation(await response.json());
  } catch (error) {
    setConversationStatus("We could not start a server conversation. Try again.", "error");
    return null;
  }
}

// The active in-memory view is only a rendering cache. Durable conversation
// state is read from /api/conversations and is never persisted by the browser.
function saveConversations() {}

function renderConversationList() {
  conversationList.innerHTML = "";
  conversationEmpty.hidden = state.conversations.length > 0;
  state.conversations.forEach((conversation) => {
    const item = document.createElement("div");
    item.className = conversation.id === state.activeConversationId ? "conversation-item active" : "conversation-item";
    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "conversation-select";
    selectButton.setAttribute("aria-current", conversation.id === state.activeConversationId ? "page" : "false");
    selectButton.innerHTML = '<span class="conversation-name"></span><span class="conversation-meta"></span>';
    selectButton.querySelector(".conversation-name").textContent = conversation.title;
    selectButton.querySelector(".conversation-meta").textContent = conversationMeta(conversation);
    selectButton.addEventListener("click", () => {
      state.activeConversationId = conversation.id;
      state.selectedAssistantMessageId = latestAssistantMessage(conversation)?.id || null;
      renderConversationList();
      renderActiveConversation();
      messageInput.focus();
    });
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "delete-conversation-button";
    deleteButton.title = `Delete ${conversation.title}`;
    deleteButton.setAttribute("aria-label", `Delete conversation ${conversation.title}`);
    deleteButton.innerHTML = '<span aria-hidden="true">×</span>';
    deleteButton.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteConversation(conversation.id);
    });
    item.appendChild(selectButton);
    item.appendChild(deleteButton);
    conversationList.appendChild(item);
  });
}

function renderActiveConversation() {
  const conversation = activeConversation();
  messages.innerHTML = "";
  if (!conversation) {
    conversationTitle.textContent = "New conversation";
    pageTitle.textContent = "How can we help today?";
    messages.appendChild(renderEmptyState());
    renderInspector();
    updateSuggestionsVisibility();
    scrollMessages();
    return;
  }
  conversationTitle.textContent = conversation.title;
  pageTitle.textContent = conversation.title === "New conversation" ? "How can we help today?" : conversation.title;
  if (!conversation.messages.length) {
    messages.appendChild(renderEmptyState());
  } else {
    conversation.messages.forEach((message) => messages.appendChild(renderMessage(message)));
  }
  renderInspector();
  updateSuggestionsVisibility();
  scrollMessages();
}

function deleteConversation(conversationId) {
  return deleteConversationAsync(conversationId);
}

async function deleteConversationAsync(conversationId) {
  if (state.sending) return;
  const conversation = state.conversations.find((candidate) => candidate.id === conversationId);
  if (!conversation) return;
  const confirmed = window.confirm(`Delete “${conversation.title}”? This conversation will be removed from the server.`);
  if (!confirmed) return;
  try {
    const response = await fetch(`/api/conversations/${encodeURIComponent(conversationId)}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { Accept: "application/json", ...sessionHeaders() },
    });
    if (response.status === 401 || response.status === 403) {
      await handleSessionExpired();
      return;
    }
    if (!response.ok) throw new Error("conversation delete failed");
  } catch (error) {
    setConversationStatus("We could not delete that server conversation. Try again.", "error");
    return;
  }
  const deletedIndex = state.conversations.findIndex((candidate) => candidate.id === conversationId);
  const wasActive = state.activeConversationId === conversationId;
  state.conversations = state.conversations.filter((candidate) => candidate.id !== conversationId);
  if (wasActive) {
    const nextConversation = state.conversations[deletedIndex] || state.conversations[deletedIndex - 1] || null;
    if (!state.conversations.length) {
      const created = await createServerConversation();
      if (created) state.conversations.push(created);
    }
    state.activeConversationId = nextConversation?.id || state.conversations[0]?.id || null;
    state.selectedAssistantMessageId = latestAssistantMessage(nextConversation)?.id || null;
  }
  saveConversations();
  renderConversationList();
  renderActiveConversation();
  setConversationStatus("Conversation deleted.");
  messageInput.focus();
}

function renderEmptyState() {
  const emptyState = document.createElement("div");
  emptyState.id = "emptyState";
  emptyState.className = "empty-state";
  emptyState.innerHTML = `
    <div class="empty-mark" aria-hidden="true">N1</div>
    <p class="eyebrow">Start with a question</p>
    <h2>Find the answer without hunting through folders.</h2>
    <p>Ask in plain language. Copilot checks your account first, then searches only the sources you can use.</p>
    <div class="capability-list" aria-label="Available question types">
      <div class="capability"><span class="capability-icon" aria-hidden="true">▤</span><span><strong>Policies</strong><small>Leave, expenses, remote work</small></span></div>
      <div class="capability"><span class="capability-icon" aria-hidden="true">↗</span><span><strong>Processes</strong><small>Access, onboarding, approvals</small></span></div>
      <div class="capability"><span class="capability-icon" aria-hidden="true">#</span><span><strong>Tickets</strong><small>Check your support requests</small></span></div>
    </div>`;
  return emptyState;
}

function renderMessage(message) {
  const statusClass = message.status === "denied"
    ? "denied"
    : ["error", "refused"].includes(message.status)
      ? "error"
      : message.status === "no_answer"
        ? "no-answer"
        : message.status === "streaming"
          ? "streaming"
          : "";
  const article = document.createElement("article");
  article.className = `message ${message.role} ${statusClass}`.trim();
  article.dataset.messageId = message.id;
  if (message.role === "assistant") {
    article.tabIndex = 0;
    const responseStatus = statusLabel(message.status);
    article.setAttribute("aria-label", responseStatus ? `Copilot response: ${responseStatus}` : "Copilot response");
    article.classList.toggle("selected", message.id === state.selectedAssistantMessageId);
    article.addEventListener("click", () => selectAssistantMessage(message.id));
    article.addEventListener("focus", () => selectAssistantMessage(message.id));
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";
  if (message.role === "user") {
    meta.textContent = "You";
  } else {
    const assistantName = document.createElement("span");
    assistantName.textContent = "Copilot";
    meta.appendChild(assistantName);
    const statusText = statusLabel(message.status);
    if (statusText) {
      const status = document.createElement("span");
      status.className = "message-status";
      status.textContent = statusText;
      meta.appendChild(status);
    }
  }
  const body = document.createElement("div");
  body.className = "message-body";
  const displayMessage = message.status === "streaming" ? message.message : (message.message || "No response was returned.");
  renderMessageBody(body, displayMessage, message.citations || [], () => {
    if (message.role === "assistant") selectAssistantMessage(message.id);
  });
  if (message.status === "streaming") article.setAttribute("aria-busy", "true");
  article.appendChild(meta);
  article.appendChild(body);
  if (message.ticket) article.appendChild(renderTicketSummary(message.ticket));
  else if (message.ticket_preview && message.approval_required) article.appendChild(renderTicketPreview(message.ticket_preview));
  else if (message.category === "own_ticket" && ["error", "refused"].includes(message.status)) article.appendChild(renderTicketStatusState());
  if (message.status === "denied") article.appendChild(renderDeniedNextStep(message));
  if (message.status === "no_answer") article.appendChild(renderNoAnswerNextStep());
  if (["error", "refused"].includes(message.status)) article.appendChild(renderRetry(message.request_text || state.lastSubmittedText, message.status === "refused" ? "Status unavailable" : "Connection issue"));
  if (message.role === "assistant" && !["error", "refused", "ready"].includes(message.status) && message.status !== "streaming") article.appendChild(renderFeedbackControls(message));
  return article;
}

function selectAssistantMessage(messageId) {
  const conversation = activeConversation();
  if (conversation) {
    conversation.messages.forEach((message) => {
      if (message.role === "assistant" && (message.trace?.length || message.subgraph_trace?.length)) {
        message.trace_expanded = message.id === messageId;
      }
    });
    saveConversations();
  }
  state.selectedAssistantMessageId = messageId;
  renderInspector();
  if (window.matchMedia("(max-width: 980px)").matches) openInspector();
  messages.querySelectorAll(".message.assistant").forEach((node) => node.classList.remove("selected"));
  messages.querySelector(`[data-message-id="${CSS.escape(messageId)}"]`)?.classList.add("selected");
}

function addUserMessage(text) {
  const conversation = activeConversation();
  if (!conversation) return;
  conversation.messages.forEach((message) => {
    if (message.role === "assistant") message.trace_expanded = false;
  });
  conversation.messages.push({ id: `user-${Date.now()}`, role: "user", message: text });
  conversation.updatedAt = new Date().toISOString();
  if (conversation.title === "New conversation") conversation.title = summarizeTitle(text);
  saveConversations();
  renderConversationList();
  renderActiveConversation();
}

function addLoadingMessage() {
  messages.querySelector("#emptyState")?.remove();
  const article = document.createElement("article");
  article.id = "loadingMessage";
  article.className = "message assistant loading";
  article.innerHTML = '<div class="message-meta"><span>Copilot</span><span class="message-status">Working</span></div><div class="loading-body"><span class="loading-dots" aria-hidden="true"><span></span><span></span><span></span></span><span>Checking access and approved sources…</span></div>';
  messages.appendChild(article);
  scrollMessages();
}

function removeLoadingMessage() {
  document.querySelector("#loadingMessage")?.remove();
}

function beginStreamingAssistantMessage() {
  const conversation = activeConversation();
  if (!conversation) return null;
  removeLoadingMessage();
  const message = {
    id: `assistant-${Date.now()}`,
    role: "assistant",
    status: "streaming",
    message: "",
    citations: [],
    sources: [],
    rows: [],
    columns: [],
    row_count: 0,
    sql_execution: null,
    model_backend: null,
    capabilities: null,
    route: null,
    category: null,
    subgraph_trace: [],
    ticket: null,
    ticket_preview: null,
    approval_required: false,
    trace_expanded: false,
    missing_fields: [],
    allowed_alternatives: [],
    trace: [],
    conversation_id: activeConversation()?.id || null,
    turn_id: null,
    request_text: state.lastSubmittedText,
  };
  conversation.messages.push(message);
  conversation.updatedAt = new Date().toISOString();
  state.streamingMessageId = message.id;
  state.selectedAssistantMessageId = message.id;
  saveConversations();
  renderConversationList();
  renderActiveConversation();
  return message;
}

function streamingAssistantMessage() {
  const conversation = activeConversation();
  if (!conversation || !state.streamingMessageId) return null;
  return conversation.messages.find((message) => message.id === state.streamingMessageId) || null;
}

function updateStreamingAssistantMessage(delta) {
  const message = streamingAssistantMessage();
  if (!message || !delta) return;
  message.message += String(delta);
  const article = messages.querySelector(`[data-message-id="${CSS.escape(message.id)}"]`);
  const body = article?.querySelector(".message-body");
  if (body) body.textContent = message.message;
  scrollMessages();
}

function removeStreamingAssistantMessage() {
  const conversation = activeConversation();
  if (!conversation || !state.streamingMessageId) return;
  conversation.messages = conversation.messages.filter((message) => message.id !== state.streamingMessageId);
  state.streamingMessageId = null;
  state.selectedAssistantMessageId = latestAssistantMessage(conversation)?.id || null;
  saveConversations();
  renderConversationList();
  renderActiveConversation();
}

function finalizeStreamingAssistantMessage(payload) {
  const message = streamingAssistantMessage();
  const conversation = activeConversation();
  if (!message || !conversation) return;
  message.status = payload.status || "answered";
  message.reason_code = payload.reason_code;
  message.route = payload.route || null;
  message.message = payload.message || message.message || "No response was returned.";
  message.citations = payload.citations || [];
  message.sources = payload.sources || [];
  message.rows = Array.isArray(payload.rows) ? payload.rows : [];
  message.columns = Array.isArray(payload.columns) ? payload.columns : [];
  message.row_count = Number.isInteger(payload.row_count) ? payload.row_count : 0;
  message.sql_execution = payload.sql_execution || null;
  message.model_backend = payload.model_backend || null;
  message.capabilities = payload.capabilities || null;
  message.category = payload.category || null;
  message.subgraph_trace = payload.subgraph_trace || [];
  message.ticket = sanitizeTicket(payload.ticket);
  message.ticket_preview = sanitizeTicketPreview(payload.ticket_preview);
  message.approval_required = payload.approval_required === true;
  message.trace_expanded = Boolean(payload.trace?.length || payload.subgraph_trace?.length);
  message.missing_fields = payload.missing_fields || [];
  message.allowed_alternatives = payload.allowed_alternatives || [];
  message.trace = payload.trace || [];
  message.conversation_id = payload.conversation_id || activeConversation()?.id || null;
  message.turn_id = payload.turn_id || null;
  message.latency_ms = payload.latency_ms;
  message.feedback = payload.feedback;
  conversation.updatedAt = new Date().toISOString();
  state.streamingMessageId = null;
  state.selectedAssistantMessageId = message.id;
  saveConversations();
  renderConversationList();
  renderActiveConversation();
  updateResponseStatus(payload);
}

function addAssistantMessage(payload) {
  const conversation = activeConversation();
  if (!conversation) return;
  const message = {
    id: `assistant-${Date.now()}`,
    role: "assistant",
    status: payload.status || "answered",
    reason_code: payload.reason_code,
    route: payload.route || null,
    message: payload.message || "No response was returned.",
    citations: payload.citations || [],
    sources: payload.sources || [],
    rows: Array.isArray(payload.rows) ? payload.rows : [],
    columns: Array.isArray(payload.columns) ? payload.columns : [],
    row_count: Number.isInteger(payload.row_count) ? payload.row_count : 0,
    sql_execution: payload.sql_execution || null,
    model_backend: payload.model_backend || null,
    capabilities: payload.capabilities || null,
    route: payload.route || null,
    category: payload.category || null,
    subgraph_trace: payload.subgraph_trace || [],
    ticket: sanitizeTicket(payload.ticket),
    ticket_preview: sanitizeTicketPreview(payload.ticket_preview),
    approval_required: payload.approval_required === true,
    trace_expanded: Boolean(payload.trace?.length || payload.subgraph_trace?.length),
    missing_fields: payload.missing_fields || [],
    allowed_alternatives: payload.allowed_alternatives || [],
    trace: payload.trace || [],
    conversation_id: payload.conversation_id || activeConversation()?.id || null,
    turn_id: payload.turn_id || null,
    latency_ms: payload.latency_ms,
    feedback: payload.feedback,
    request_text: payload.request_text || state.lastSubmittedText,
  };
  conversation.messages.push(message);
  conversation.updatedAt = new Date().toISOString();
  state.selectedAssistantMessageId = message.id;
  saveConversations();
  renderConversationList();
  renderActiveConversation();
  updateResponseStatus(payload);
}

function collectSourceItems(payload) {
  const citations = Array.isArray(payload.citations) ? payload.citations : [];
  const sources = Array.isArray(payload.sources) ? payload.sources : [];
  return [...citations, ...sources];
}

function sanitizeTicket(ticket) {
  if (!ticket || typeof ticket !== "object") return null;
  const safe = {};
  ["ticket_id", "requester", "department", "category", "priority", "description", "created_at", "updated_at"].forEach((field) => {
    if (ticket[field] != null && String(ticket[field]).trim()) safe[field] = String(ticket[field]).trim();
  });
  if (ticket.status != null) safe.status = safeTicketStatus(ticket.status) || "unavailable";
  return Object.keys(safe).length ? safe : null;
}

function sanitizeTicketPreview(preview) {
  if (!preview || typeof preview !== "object") return null;
  const safe = {};
  ["requester", "department", "category", "priority", "description"].forEach((field) => {
    if (preview[field] != null && String(preview[field]).trim()) safe[field] = String(preview[field]).trim();
  });
  return Object.keys(safe).length ? safe : null;
}

function safeTicketStatus(value) {
  const normalized = String(value || "").trim().toLowerCase();
  const allowed = new Set(["created", "open", "in progress", "pending", "waiting on user", "resolved", "closed", "error", "unavailable"]);
  if (!allowed.has(normalized.replaceAll("_", " "))) return normalized.length <= 24 && /^[a-z0-9 -]+$/.test(normalized) ? normalized : null;
  return normalized.replaceAll("_", " ");
}

function renderTicketSummary(ticket) {
  const safeTicket = sanitizeTicket(ticket);
  if (!safeTicket) return document.createDocumentFragment();
  if (!safeTicket.status) safeTicket.status = "unavailable";
  const section = document.createElement("section");
  section.className = "ticket-summary";
  const title = document.createElement("h3");
  title.textContent = safeTicket.status === "error" || safeTicket.status === "unavailable" ? "Ticket status" : "Ticket details";
  const list = document.createElement("dl");
  [["ID", safeTicket.ticket_id], ["Requester", safeTicket.requester], ["Status", safeTicket.status], ["Team", safeTicket.department], ["Category", safeTicket.category], ["Priority", safeTicket.priority], ["Details", safeTicket.description], ["Updated", safeTicket.updated_at ? formatTimestamp(safeTicket.updated_at) : null]].forEach(([label, value]) => {
    if (!value) return;
    const row = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    row.appendChild(term);
    row.appendChild(detail);
    list.appendChild(row);
  });
  section.appendChild(title);
  section.appendChild(list);
  if (state.account && ["hr", "it_admin", "admin_ops"].includes(state.account.role)
      && ["open", "in progress", "waiting on user", "resolved"].includes(String(safeTicket.status || "").replaceAll("_", " "))) {
    const action = document.createElement("button");
    action.type = "button";
    action.className = "button button-secondary ticket-close-action";
    action.textContent = "Close ticket";
    action.addEventListener("click", () => closeTicketFromView(safeTicket));
    section.appendChild(action);
  }
  return section;
}

async function closeTicketFromView(ticket) {
  const comment = window.prompt("Add a non-empty closing comment or resolution detail:");
  if (!comment || !comment.trim()) {
    setConversationStatus("A closing comment or details is required.", "error");
    return;
  }
  try {
    const response = await fetch(`/api/tickets/${encodeURIComponent(ticket.ticket_id)}/close`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json", ...sessionHeaders() },
      body: JSON.stringify({ comment }),
    });
    const result = await response.json();
    if (response.status === 401 || response.status === 403) {
      await handleSessionExpired();
      return;
    }
    if (!response.ok || result.status !== "ticket_closed") {
      setConversationStatus(result.message || "That ticket could not be closed.", "error");
      return;
    }
    ticket.status = "closed";
    ticket.updated_at = result.ticket?.updated_at || ticket.updated_at;
    saveConversations();
    renderActiveConversation();
    setConversationStatus("Ticket status updated to closed.");
  } catch (error) {
    setConversationStatus("We could not update that ticket. Try again.", "error");
  }
}

function renderTicketPreview(preview) {
  const safePreview = sanitizeTicketPreview(preview);
  if (!safePreview) return document.createDocumentFragment();
  const section = document.createElement("section");
  section.className = "ticket-summary ticket-preview";
  const title = document.createElement("h3");
  title.textContent = "Review before creating";
  const list = document.createElement("dl");
  [["Requester", safePreview.requester], ["Team", safePreview.department], ["Category", safePreview.category], ["Priority", safePreview.priority], ["Details", safePreview.description]].forEach(([label, value]) => {
    if (!value) return;
    const row = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    row.appendChild(term);
    row.appendChild(detail);
    list.appendChild(row);
  });
  const note = document.createElement("p");
  note.className = "ticket-preview-note";
  note.textContent = "This is a preview. Nothing is created until you explicitly approve it.";
  const actions = document.createElement("div");
  actions.className = "ticket-preview-actions";
  [["Approve ticket", "Approve ticket"], ["Cancel ticket", "Cancel ticket"]].forEach(([label, text]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = label.startsWith("Approve") ? "button button-primary" : "button button-secondary";
    button.textContent = label;
    button.addEventListener("click", () => sendMessage(text));
    actions.appendChild(button);
  });
  section.appendChild(title);
  section.appendChild(list);
  section.appendChild(note);
  section.appendChild(actions);
  return section;
}

function renderTicketStatusState() {
  const section = document.createElement("section");
  section.className = "ticket-summary ticket-status-unavailable";
  const title = document.createElement("h3");
  title.textContent = "Ticket status";
  const status = document.createElement("p");
  status.textContent = "Status unavailable";
  section.appendChild(title);
  section.appendChild(status);
  return section;
}

function renderFeedbackControls(payload) {
  const section = document.createElement("section");
  section.className = "feedback";
  section.setAttribute("aria-label", "Answer feedback");
  [["helpful", "Helpful"], ["not_helpful", "Not helpful"], ["missing_source", "Source issue"]].forEach(([rating, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "feedback-button";
    button.dataset.rating = rating;
    button.dataset.actionLabel = label;
    button.title = label;
    button.setAttribute("aria-label", label);
    button.innerHTML = `${feedbackIcon(rating)}<span class="sr-only">${label}</span>`;
    button.addEventListener("click", () => sendFeedback(button, payload, rating));
    section.appendChild(button);
  });
  return section;
}

function feedbackIcon(rating, saved = false) {
  if (saved) {
    return '<svg class="feedback-icon" data-icon="saved" viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" /></svg>';
  }
  const icons = {
    helpful: '<svg class="feedback-icon" data-icon="thumbs-up" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10v10H4a1 1 0 0 1-1-1v-8a1 1 0 0 1 1-1h3Zm0 10h9.4a2 2 0 0 0 1.94-1.52l1.2-4.8A2 2 0 0 0 17.6 11H14l.76-3.8A2.6 2.6 0 0 0 12.22 4L7 10v10Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.7" /></svg>',
    not_helpful: '<svg class="feedback-icon" data-icon="thumbs-down" viewBox="0 0 24 24" aria-hidden="true"><path d="M7 14V4H4a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h3Zm0-10h9.4a2 2 0 0 1 1.94 1.52l1.2 4.8A2 2 0 0 1 17.6 13H14l.76 3.8A2.6 2.6 0 0 1 12.22 20L7 14V4Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.7" /></svg>',
    missing_source: '<svg class="feedback-icon" data-icon="source-issue" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h8l4 4v14H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" stroke-linejoin="round" stroke-width="1.7" /><path d="M14 3v5h5M12 11v4M12 18h.01" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" /></svg>',
  };
  return icons[rating] || icons.missing_source;
}

async function sendFeedback(button, payload, rating) {
  const actionLabel = button.dataset.actionLabel || rating;
  button.disabled = true;
  button.setAttribute("aria-label", `${actionLabel} saving`);
  button.title = `${actionLabel} saving`;
  try {
    const response = await fetch("/api/feedback", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json", ...sessionHeaders() },
      body: JSON.stringify({
        conversation_id: payload.conversation_id || activeConversation()?.id || null,
        turn_id: payload.turn_id || null,
        rating,
      }),
    });
    const result = await response.json();
    if (response.status === 401 || response.status === 403) {
      await handleSessionExpired();
      return;
    }
    if (response.ok && result.status === "stored") {
      payload.feedback = rating;
      button.innerHTML = `${feedbackIcon(rating, true)}<span class="sr-only">${actionLabel} saved</span>`;
      button.title = `${actionLabel} saved`;
      button.setAttribute("aria-label", `${actionLabel} saved`);
      button.classList.add("is-saved");
      saveConversations();
      renderInspector();
    } else {
      const errorLabel = `${actionLabel}: ${result.message || "Could not save"}`;
      button.innerHTML = `${feedbackIcon(rating)}<span class="sr-only">${errorLabel}</span>`;
      button.title = errorLabel;
      button.setAttribute("aria-label", errorLabel);
    }
  } catch (error) {
    const errorLabel = `${actionLabel}: Could not save`;
    button.innerHTML = `${feedbackIcon(rating)}<span class="sr-only">${errorLabel}</span>`;
    button.title = errorLabel;
    button.setAttribute("aria-label", errorLabel);
  } finally {
    window.setTimeout(() => {
      if (payload.feedback === rating) {
        const savedLabel = `${actionLabel} saved`;
        button.innerHTML = `${feedbackIcon(rating, true)}<span class="sr-only">${savedLabel}</span>`;
        button.title = savedLabel;
        button.setAttribute("aria-label", savedLabel);
        button.classList.add("is-saved");
      } else {
        button.innerHTML = `${feedbackIcon(rating)}<span class="sr-only">${actionLabel}</span>`;
        button.title = actionLabel;
        button.setAttribute("aria-label", actionLabel);
        button.classList.remove("is-saved");
      }
      button.disabled = false;
    }, 1200);
  }
}

function renderMessageBody(container, text, citations, beforeCitationSelect = null) {
  container.textContent = "";
  const sourceIds = new Set(citations.map((citation) => Number(citation.reference_id)).filter((referenceId) => Number.isInteger(referenceId)));
  const parts = String(text).split(/(\[\d+\])/g);
  parts.forEach((part) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (!match || !sourceIds.has(Number(match[1]))) {
      container.appendChild(document.createTextNode(part));
      return;
    }
    const referenceId = Number(match[1]);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "citation-ref";
    button.textContent = part;
    button.setAttribute("aria-label", `Show source ${referenceId}`);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      if (beforeCitationSelect) beforeCitationSelect();
      window.requestAnimationFrame(() => selectSource(referenceId));
    });
    container.appendChild(button);
  });
}

function selectSource(referenceId) {
  openInspector();
  const source = document.querySelector(`#source-${referenceId}`);
  if (!source) return;
  source.scrollIntoView({ behavior: "smooth", block: "nearest" });
  source.focus({ preventScroll: true });
}

function setIconControlLabel(control, label) {
  control.setAttribute("aria-label", label);
  control.title = label;
  const accessibleLabel = control.querySelector(".sr-only");
  if (accessibleLabel) accessibleLabel.textContent = label;
}

function closeInspector() {
  inspector.classList.remove("open");
  inspector.classList.add("is-collapsed");
  appView.classList.add("right-inspector-collapsed");
  setIconControlLabel(closeInspectorButton, "Expand conversation details");
  closeInspectorButton.querySelector(".panel-toggle-icon").textContent = ">";
}

function openInspector() {
  inspector.classList.remove("is-collapsed");
  inspector.classList.add("open");
  appView.classList.remove("right-inspector-collapsed");
  setIconControlLabel(closeInspectorButton, "Collapse conversation details");
  closeInspectorButton.querySelector(".panel-toggle-icon").textContent = ">";
}

function setSidebarExpanded(expanded) {
  conversationRail.classList.toggle("is-collapsed", !expanded);
  appView.classList.toggle("left-sidebar-collapsed", !expanded);
  leftSidebarToggle.setAttribute("aria-expanded", String(expanded));
  setIconControlLabel(leftSidebarToggle, expanded ? "Collapse navigation" : "Expand navigation");
  leftSidebarToggle.querySelector(".sidebar-toggle-icon").textContent = expanded ? "‹" : "›";
}

function renderInspector() {
  const message = selectedAssistantMessage();
  inspectorContent.innerHTML = "";
  if (!message) {
    inspectorContent.innerHTML = '<p class="empty-note">Select an answer to inspect sources, ticket details, feedback, and trace output.</p>';
    return;
  }
  if (message.ticket) inspectorContent.appendChild(renderTicketSummary(message.ticket));
  else if (message.ticket_preview && message.approval_required) inspectorContent.appendChild(renderTicketPreview(message.ticket_preview));
  else if (message.category === "own_ticket" && ["error", "refused"].includes(message.status)) inspectorContent.appendChild(renderTicketStatusState());
  if (message.rows.length) inspectorContent.appendChild(renderStructuredRows(message));
  const sourceItems = collectSourceItems(message);
  if (sourceItems.length) inspectorContent.appendChild(renderSources(sourceItems));
  if (message.missing_fields && message.missing_fields.length) {
    const section = document.createElement("section");
    section.className = "detail-section";
    const heading = document.createElement("h3");
    heading.textContent = "Missing details";
    const list = document.createElement("ul");
    message.missing_fields.forEach((field) => {
      const item = document.createElement("li");
      item.textContent = field;
      list.appendChild(item);
    });
    section.appendChild(heading);
    section.appendChild(list);
    inspectorContent.appendChild(section);
  }
  const meta = document.createElement("section");
  meta.className = "detail-section";
  meta.innerHTML = `
    <h3>Answer metadata</h3>
    <dl>
      <div><dt>Status</dt><dd>${escapeHtml(message.status || "answered")}</dd></div>
      <div><dt>Reason</dt><dd>${escapeHtml(message.reason_code || "-")}</dd></div>
      <div><dt>Route</dt><dd>${escapeHtml(message.route || "-")}</dd></div>
      <div><dt>Latency</dt><dd>${message.latency_ms == null ? "-" : `${message.latency_ms}ms`}</dd></div>
      <div><dt>Structured rows</dt><dd>${message.row_count || 0}</dd></div>
      <div><dt>Feedback</dt><dd>${escapeHtml(message.feedback || "Not submitted")}</dd></div>
    </dl>`;
  inspectorContent.appendChild(meta);
  if ((message.trace && message.trace.length) || (message.subgraph_trace && message.subgraph_trace.length)) {
    inspectorContent.appendChild(renderTrace(message.trace || [], message.subgraph_trace || [], message.trace_expanded !== false, (expanded) => {
      message.trace_expanded = expanded;
      saveConversations();
    }));
  }
}

function selectedAssistantMessage() {
  const conversation = activeConversation();
  if (!conversation) return null;
  return conversation.messages.find((message) => message.id === state.selectedAssistantMessageId && message.role === "assistant") || null;
}

function latestAssistantMessage(conversation) {
  if (!conversation) return null;
  return [...conversation.messages].reverse().find((message) => message.role === "assistant") || null;
}

function displayStructuredValue(column, value) {
  if (value == null) return "—";
  if (["created_at", "updated_at", "last_updated"].includes(String(column).toLowerCase())) {
    return formatTimestamp(value);
  }
  return String(value);
}

function renderStructuredRows(message) {
  const section = document.createElement("section");
  section.className = "structured-results";
  const title = document.createElement("h3");
  title.textContent = `Structured data · ${message.row_count || message.rows.length} row(s)`;
  section.appendChild(title);
  const wrapper = document.createElement("div");
  wrapper.className = "structured-results-scroll";
  const table = document.createElement("table");
  table.className = "structured-results-table";
  const columns = message.columns.length ? message.columns : Object.keys(message.rows[0] || {});
  const head = document.createElement("thead");
  const headRow = document.createElement("tr");
  columns.forEach((column) => {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = column;
    headRow.appendChild(cell);
  });
  head.appendChild(headRow);
  table.appendChild(head);
  const body = document.createElement("tbody");
  message.rows.forEach((row) => {
    const tableRow = document.createElement("tr");
    columns.forEach((column) => {
      const cell = document.createElement("td");
      const value = row && row[column] != null ? row[column] : "—";
      cell.textContent = displayStructuredValue(column, value);
      tableRow.appendChild(cell);
    });
    body.appendChild(tableRow);
  });
  table.appendChild(body);
  wrapper.appendChild(table);
  section.appendChild(wrapper);
  return section;
}

function renderSources(items) {
  const section = document.createElement("section");
  section.className = "sources";
  const title = document.createElement("h3");
  title.textContent = "Approved sources";
  const list = document.createElement("div");
  list.className = "source-list";
  items.forEach((item) => list.appendChild(renderSourceCard(item)));
  section.appendChild(title);
  section.appendChild(list);
  return section;
}

function renderSourceCard(item) {
  const card = document.createElement("article");
  card.className = "source-card";
  const referenceId = item.reference_id;
  if (referenceId) {
    card.id = `source-${referenceId}`;
    card.tabIndex = -1;
  }
  const header = document.createElement("div");
  header.className = "source-header";
  const label = document.createElement("span");
  label.className = "source-label";
  label.textContent = item.label || (referenceId ? `[${referenceId}]` : "SQL");
  const heading = document.createElement("h4");
  heading.textContent = item.title || item.name || "Source";
  header.appendChild(label);
  header.appendChild(heading);
  card.appendChild(header);
  const meta = document.createElement("p");
  meta.className = "source-meta";
  meta.textContent = sourceMeta(item);
  card.appendChild(meta);
  const sourceText = item.text || item.excerpt;
  if (sourceText) {
    const excerpt = document.createElement("blockquote");
    excerpt.className = "source-excerpt";
    excerpt.textContent = sourceText;
    card.appendChild(excerpt);
  }
  return card;
}

function formatTimestamp(value) {
  if (value == null) return "Timestamp unavailable";
  const raw = String(value).trim();
  if (!raw) return "Timestamp unavailable";
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(raw);
  let normalized = raw.replace(/\s+(?:UT|UTC)$/i, "Z");
  if (normalized.includes(" ") && !normalized.includes("T")) normalized = normalized.replace(" ", "T");
  if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(normalized)) normalized += "Z";
  if (!isValidIsoCalendarDate(normalized)) return "Timestamp unavailable";
  const parsed = new Date(normalized);
  if (Number.isNaN(parsed.getTime())) return "Timestamp unavailable";
  const locale = typeof navigator !== "undefined" && navigator.language ? navigator.language : "en-US";
  const options = dateOnly
    ? { year: "numeric", month: "short", day: "numeric", timeZone: DISPLAY_TIME_ZONE, timeZoneName: "short" }
    : { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: DISPLAY_TIME_ZONE, timeZoneName: "short" };
  try {
    const formatted = new Intl.DateTimeFormat(locale, options).format(parsed);
    return /\bUTC\b/.test(formatted) ? formatted : `${formatted} UTC`;
  } catch (error) {
    return "Timestamp unavailable";
  }
}

function isValidIsoCalendarDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!match) return true;
  const candidate = new Date(`${match[1]}-${match[2]}-${match[3]}T00:00:00Z`);
  return candidate.getUTCFullYear() === Number(match[1])
    && candidate.getUTCMonth() + 1 === Number(match[2])
    && candidate.getUTCDate() === Number(match[3]);
}

if (typeof window !== "undefined") window.NexusOneTimeDisplay = { formatTimestamp };

function sourceMeta(item) {
  if (!item.title) return `${item.kind || "structured source"}${item.domain ? ` · ${item.domain}` : ""}`;
  const details = [item.source_type || "document"];
  if (item.page_number) details.push(`page ${item.page_number}`);
  if (item.section_heading) details.push(item.section_heading);
  if (item.updated_at) details.push(`updated ${formatTimestamp(item.updated_at)}`);
  if (item.source_path) details.push(item.source_path);
  return details.join(" · ");
}

function renderTrace(trace, subgraphTrace = [], expanded = true, onToggle = null) {
  const section = document.createElement("details");
  section.className = "trace";
  section.open = expanded;
  const summary = document.createElement("summary");
  summary.textContent = "Trace for this answer";
  summary.addEventListener("click", (event) => event.stopPropagation());
  section.appendChild(summary);
  const title = document.createElement("h3");
  title.textContent = "Graph trace";
  section.appendChild(title);
  section.appendChild(renderTraceList(trace));
  if (subgraphTrace.length) {
    const subgraphTitle = document.createElement("h3");
    subgraphTitle.textContent = "SQL subgraph trace";
    section.appendChild(subgraphTitle);
    section.appendChild(renderTraceList(subgraphTrace));
  }
  if (onToggle) section.addEventListener("toggle", () => onToggle(section.open));
  return section;
}

function renderTraceList(trace) {
  const list = document.createElement("ol");
  trace.forEach((item) => {
    const li = document.createElement("li");
    const details = item.details || {};
    li.textContent = `${item.node}: ${item.status || details.status || "running"}`;
    list.appendChild(li);
  });
  return list;
}

function renderDeniedNextStep(payload) {
  const section = document.createElement("section");
  section.className = "message-next-step";
  const title = document.createElement("h3");
  title.textContent = "What you can ask instead";
  const alternatives = Array.isArray(payload.allowed_alternatives) && payload.allowed_alternatives.length
    ? payload.allowed_alternatives
    : ["public company policies", "your own support tickets", "general process guidance"];
  const copy = document.createElement("p");
  copy.textContent = alternatives.join(" · ");
  section.appendChild(title);
  section.appendChild(copy);
  return section;
}

function renderNoAnswerNextStep() {
  const section = document.createElement("section");
  section.className = "message-next-step";
  const title = document.createElement("h3");
  title.textContent = "Try making the question more specific";
  const copy = document.createElement("p");
  copy.textContent = "Include the policy, process, or ticket reference you want to look up.";
  section.appendChild(title);
  section.appendChild(copy);
  return section;
}

function renderRetry(text, titleText = "Connection issue") {
  const section = document.createElement("section");
  section.className = "message-next-step";
  const title = document.createElement("h3");
  title.textContent = titleText;
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "retry-button";
  retry.textContent = "Try again";
  retry.addEventListener("click", () => sendMessage(text));
  section.appendChild(title);
  section.appendChild(retry);
  return section;
}

function setAuthenticating(value) {
  state.authenticating = value;
  loginButton.disabled = value;
  loginButton.setAttribute("aria-busy", String(value));
  loginButton.classList.toggle("is-loading", value);
  loginButtonLoader.hidden = !value;
  usernameInput.disabled = value;
  passwordInput.disabled = value;
  loginButtonLabel.textContent = value ? "Signing in…" : "Sign in";
}

function setSending(value) {
  state.sending = value;
  sendButton.disabled = value || !activeAccount() || !messageInput.value.trim();
  const label = sendButton.querySelector("span");
  if (label) label.textContent = value ? "Checking" : "Send";
  messageInput.disabled = value || !activeAccount();
  conversationList.querySelectorAll(".delete-conversation-button").forEach((button) => { button.disabled = value; });
  updateSuggestionsVisibility();
  if (value) {
    setConversationStatus("Checking access and approved sources…", "busy");
    addLoadingMessage();
  }
}

function setComposerAvailability() {
  if (!sendButton || !messageInput) return;
  sendButton.disabled = state.sending || !activeAccount() || !messageInput.value.trim();
  messageInput.disabled = state.sending || !activeAccount();
}

function parseStreamEvent(frame) {
  const lines = frame.split(/\r?\n/);
  let eventName = "";
  const dataLines = [];
  lines.forEach((line) => {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  });
  if (!eventName || !dataLines.length) throw new Error("Malformed response event");
  const payload = JSON.parse(dataLines.join("\n"));
  if (!payload || payload.type !== eventName) throw new Error("Mismatched response event type");
  return payload;
}

async function consumeStream(response, onEvent) {
  if (!response.body || typeof response.body.getReader !== "function") throw new Error("Streaming is not supported by this browser.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let malformedCount = 0;
  let completion = null;
  let terminalError = null;
  try {
    while (true) {
      const result = await reader.read();
      buffer += decoder.decode(result.value || new Uint8Array(), { stream: !result.done });
      let separator;
      while ((separator = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, separator);
        buffer = buffer.slice(separator + 2);
        if (!frame.trim()) continue;
        try {
          const event = parseStreamEvent(frame);
          if (event.type === "response.complete") completion = event;
          if (event.type === "response.error" && !event.recoverable) terminalError = event;
          onEvent(event);
        } catch (error) {
          malformedCount += 1;
          setConversationStatus("A response event was malformed; continuing safely.", "error");
        }
      }
      if (result.done) break;
    }
    const remainder = buffer.trim();
    if (remainder) {
      try {
        const event = parseStreamEvent(remainder);
        if (event.type === "response.complete") completion = event;
        if (event.type === "response.error" && !event.recoverable) terminalError = event;
        onEvent(event);
      } catch (error) {
        malformedCount += 1;
      }
    }
  } finally {
    reader.releaseLock();
  }
  if (completion) return completion;
  if (terminalError) return terminalError;
  throw new Error(malformedCount ? "The response stream contained malformed events." : "The response stream ended before completion.");
}

async function sendMessage(text, options = {}) {
  const cleanText = String(text || "").trim();
  if (!cleanText || state.sending || !activeAccount()) return;
  if (options.addUser !== false) addUserMessage(cleanText);
  state.lastSubmittedText = cleanText;
  setSending(true);
  const controller = new AbortController();
  state.activeStreamController = controller;
  let streamStarted = false;
  let terminalEventHandled = false;
  try {
    const requestBody = { message: cleanText, include_trace: traceToggle.checked };
    if (activeConversation()?.id) requestBody.conversation_id = activeConversation().id;
    // Legacy-compatible shape: body: JSON.stringify({ message: cleanText, include_trace: traceToggle.checked })
    const response = await fetch("/api/chat", {
      method: "POST",
      credentials: "same-origin",
      signal: controller.signal,
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...sessionHeaders() },
      body: JSON.stringify(requestBody),
    });
    if (response.status === 401 || response.status === 403) {
      await handleSessionExpired();
      return;
    }
    if (!response.ok) {
      let payload = {};
      try { payload = await response.json(); } catch (error) { /* use generic copy */ }
      throw new Error(payload.message || `Chat request failed: ${response.status}`);
    }
    const result = await consumeStream(response, (event) => {
      if (event.type === "response.start") {
        if (!streamStarted) {
          beginStreamingAssistantMessage();
          streamStarted = true;
        }
        setConversationStatus("Copilot is writing…", "busy");
      } else if (event.type === "response.delta") {
        if (!streamStarted) {
          beginStreamingAssistantMessage();
          streamStarted = true;
        }
        updateStreamingAssistantMessage(event.delta || "");
      } else if (event.type === "response.error") {
        if (event.recoverable) {
          setConversationStatus(event.message || "The primary provider is unavailable; finishing locally.", "busy");
        } else {
          terminalEventHandled = true;
          finalizeStreamingAssistantMessage({
            status: "error",
            reason_code: event.reason_code || "STREAM_ERROR",
            message: event.message || "We could not complete that request. Try again in a moment.",
          });
          setConversationStatus("The request could not be completed. You can try again.", "error");
        }
      } else if (event.type === "response.complete") {
        finalizeStreamingAssistantMessage(event.response || {});
      }
    });
    if (result.type === "response.complete") {
      if (!terminalEventHandled) finalizeStreamingAssistantMessage(result.response || {});
    } else if (result.type === "response.error" && !terminalEventHandled) {
      terminalEventHandled = true;
      finalizeStreamingAssistantMessage({
        status: "error",
        reason_code: result.reason_code || "STREAM_ERROR",
        message: result.message || "We could not complete that request. Try again in a moment.",
      });
      setConversationStatus("The request could not be completed. You can try again.", "error");
    }
  } catch (error) {
    if (error?.name === "AbortError") {
      removeStreamingAssistantMessage();
      setConversationStatus("Request stopped.");
    } else {
      if (streamStarted && !terminalEventHandled) {
        finalizeStreamingAssistantMessage({
          status: "error",
          request_text: cleanText,
          message: "We could not complete that request. Try again in a moment.",
        });
      } else {
        addAssistantMessage({
          status: "error",
          request_text: cleanText,
          message: "We could not complete that request. Try again in a moment.",
        });
      }
      setConversationStatus("The request could not be completed. You can try again.", "error");
    }
  } finally {
    if (state.activeStreamController === controller) state.activeStreamController = null;
    removeLoadingMessage();
    setSending(false);
    messageInput.value = "";
    autoResizeComposer();
    if (activeAccount()) messageInput.focus();
  }
}

function updateResponseStatus(payload) {
  if (payload.status === "denied") {
    setConversationStatus("This request was stopped before restricted sources were searched.");
  } else if (payload.status === "error" || payload.status === "refused") {
    setConversationStatus("The request needs attention.", "error");
  } else {
    setConversationStatus("");
  }
}

function updateSuggestionsVisibility() {
  const conversation = activeConversation();
  const hasSubmittedResponse = state.sending || Boolean(conversation?.messages.some((message) => message.role === "assistant"));
  suggestions.hidden = hasSubmittedResponse;
  suggestions.setAttribute("aria-hidden", String(hasSubmittedResponse));
}

function setConversationStatus(text, stateName = "") {
  conversationStatus.textContent = text;
  conversationStatus.className = `conversation-status ${stateName ? `is-${stateName}` : ""}`.trim();
}

function autoResizeComposer() {
  if (!messageInput) return;
  messageInput.style.height = "auto";
  const nextHeight = Math.min(messageInput.scrollHeight, MAX_COMPOSER_HEIGHT);
  messageInput.style.height = `${Math.max(nextHeight, 44)}px`;
  messageInput.style.overflowY = messageInput.scrollHeight > MAX_COMPOSER_HEIGHT ? "auto" : "hidden";
}

function startNewChat() {
  return startNewChatAsync();
}

async function startNewChatAsync() {
  if (state.sending) return;
  const conversation = await createServerConversation();
  if (!conversation) return;
  state.conversations.unshift(conversation);
  state.activeConversationId = conversation.id;
  state.selectedAssistantMessageId = null;
  saveConversations();
  renderConversationList();
  renderActiveConversation();
  setConversationStatus("");
  messageInput.focus();
}

function scrollMessages() {
  messages.scrollTop = messages.scrollHeight;
}

function summarizeTitle(text) {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > 44 ? `${clean.slice(0, 41)}...` : clean || "New conversation";
}

function conversationMeta(conversation) {
  const count = conversation.messages.length;
  const date = new Date(conversation.updatedAt);
  const label = Number.isNaN(date.getTime()) ? "Saved" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return `${count} message${count === 1 ? "" : "s"} · ${label}`;
}

function setAuthError(text) {
  authError.textContent = text || "";
}

function setAuthStatus(text) {
  authStatus.textContent = text || "";
}

function clearAuthMessage() {
  setAuthError("");
  setAuthStatus("");
}

function setAuthServiceState(text, stateName = "") {
  authServiceStatus.textContent = text;
  authServiceIndicator.className = `status-dot ${stateName ? `is-${stateName}` : ""}`.trim();
}

function authServiceError(status) {
  if (status === 404) return "Sign-in service is not configured";
  if (status >= 500) return "Sign-in service is unavailable";
  return `Sign-in service returned an error (${status})`;
}

function payloadMessage(payload) {
  return typeof payload?.message === "string" ? payload.message : "";
}

function statusLabel(status) {
  const labels = { denied: "Access limited", error: "Needs attention", refused: "Needs attention", needs_approval: "Approval needed", needs_clarification: "More details needed", not_created: "Not created", streaming: "Writing…" };
  return labels[status] || "";
}

function formatRole(role) {
  const formatted = String(role || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
  return formatted
    .replace(/\bHr\b/g, "HR")
    .replace(/\bIt\b/g, "IT")
    .replace(/\bCeo\b/g, "CEO");
}

function initials(name) {
  return String(name || "N1").split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join("");
}

function escapeHtml(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

loginForm.addEventListener("submit", submitLogin);
accountButton.addEventListener("click", toggleAccountPopover);
accountButton.addEventListener("focus", openAccountPopover);
logoutButton.addEventListener("click", logout);
newChatButton.addEventListener("click", startNewChat);
leftSidebarToggle.addEventListener("click", () => {
  const expanded = leftSidebarToggle.getAttribute("aria-expanded") === "true";
  setSidebarExpanded(!expanded);
  leftSidebarToggle.focus();
});
closeInspectorButton.addEventListener("click", closeInspector);
chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(messageInput.value);
});
messageInput.addEventListener("input", () => {
  setComposerAvailability();
  autoResizeComposer();
});
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});
suggestions.addEventListener("click", (event) => {
  const button = event.target.closest("[data-prompt]");
  if (!button || state.sending || !activeAccount()) return;
  messageInput.value = button.dataset.prompt || "";
  setComposerAvailability();
  autoResizeComposer();
  messageInput.focus();
});
document.addEventListener("click", (event) => {
  if (!accountPopover.hidden && !event.target.closest(".account-control-wrap")) closeAccountPopover();
});
window.addEventListener("pagehide", () => state.activeStreamController?.abort());
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    if (!accountPopover.hidden) {
      closeAccountPopover();
      if (document.activeElement !== accountButton) {
        skipNextAccountFocus = true;
        accountButton.focus();
        window.setTimeout(() => { skipNextAccountFocus = false; }, 0);
      }
    } else if (inspector.classList.contains("open")) {
      closeInspector();
    }
  }
});
accountPopover.addEventListener("click", (event) => event.stopPropagation());

setComposerAvailability();
autoResizeComposer();
init();
