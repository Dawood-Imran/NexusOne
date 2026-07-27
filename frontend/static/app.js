const STORAGE_PREFIX = "nexusone.conversations.";
const AUTH_ENDPOINTS = {
  session: "/api/auth/session",
  login: "/api/auth/login",
  logout: "/api/auth/logout",
};
const MAX_COMPOSER_HEIGHT = 168;

const state = {
  account: null,
  sessionToken: null,
  conversations: [],
  activeConversationId: null,
  selectedAssistantMessageId: null,
  sending: false,
  authenticating: false,
  lastSubmittedText: "",
  sessionExpiredHandled: false,
};

const authView = document.querySelector("#authView");
const appView = document.querySelector("#appView");
const loginForm = document.querySelector("#loginForm");
const usernameInput = document.querySelector("#usernameInput");
const passwordInput = document.querySelector("#passwordInput");
const loginButton = document.querySelector("#loginButton");
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
const characterCount = document.querySelector("#characterCount");
const sendButton = document.querySelector("#sendButton");
const traceToggle = document.querySelector("#traceToggle");
const conversationStatus = document.querySelector("#conversationStatus");
const suggestions = document.querySelector("#suggestions");
const inspector = document.querySelector("#inspector");
const inspectorContent = document.querySelector("#inspectorContent");
const mobileInspectorButton = document.querySelector("#mobileInspectorButton");
const closeInspectorButton = document.querySelector("#closeInspectorButton");
const serviceStatus = document.querySelector("#serviceStatus");
const serviceStatusIndicator = document.querySelector("#serviceStatusIndicator");
const capabilityStatus = document.querySelector("#capabilityStatus");
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
    enterWorkspace(account, authToken(payload));
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
    enterWorkspace(account, authToken(payload));
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
  state.account = account;
  state.sessionToken = sessionToken;
  state.sessionExpiredHandled = false;
  state.conversations = loadConversations(account.user_id);
  if (!state.conversations.length) {
    state.conversations.push(createConversation());
    saveConversations();
  }
  state.activeConversationId = state.conversations[0].id;
  state.selectedAssistantMessageId = latestAssistantMessage(activeConversation())?.id || null;
  authView.classList.add("hidden");
  appView.classList.remove("hidden");
  updateAccountControl();
  renderConversationList();
  renderActiveConversation();
  setConversationStatus("Ready when you are.");
  setServiceState("Session ready", "live");
  capabilityStatus.textContent = "Access checked";
  setSidebarExpanded(true);
  if (window.matchMedia("(min-width: 981px)").matches) openInspector();
  else closeInspector();
  setComposerAvailability();
  autoResizeComposer();
  messageInput.focus();
}

function showLogin() {
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
  setAuthServiceState(logoutFailed ? "Sign-in service did not confirm sign out" : "Signed out", logoutFailed ? "error" : "live");
  setAuthStatus(logoutFailed ? "You were signed out on this device. The service could not confirm the server session; try again before sharing this device." : "You are signed out.");
  if (logoutFailed) setAuthError("The server did not confirm sign out. Sign in again only when you are ready.");
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

function createConversation(title = "New conversation") {
  const now = new Date().toISOString();
  return {
    id: `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    title,
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

function loadConversations(userId) {
  try {
    const raw = window.localStorage.getItem(`${STORAGE_PREFIX}${userId}`);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    return [];
  }
}

function saveConversations() {
  if (!state.account) return;
  window.localStorage.setItem(`${STORAGE_PREFIX}${state.account.user_id}`, JSON.stringify(state.conversations.slice(0, 30)));
}

function renderConversationList() {
  conversationList.innerHTML = "";
  conversationEmpty.hidden = state.conversations.length > 0;
  state.conversations.forEach((conversation) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = conversation.id === state.activeConversationId ? "conversation-item active" : "conversation-item";
    button.innerHTML = '<span class="conversation-name"></span><span class="conversation-meta"></span>';
    button.querySelector(".conversation-name").textContent = conversation.title;
    button.querySelector(".conversation-meta").textContent = conversationMeta(conversation);
    button.addEventListener("click", () => {
      state.activeConversationId = conversation.id;
      state.selectedAssistantMessageId = latestAssistantMessage(conversation)?.id || null;
      renderConversationList();
      renderActiveConversation();
      messageInput.focus();
    });
    conversationList.appendChild(button);
  });
}

function renderActiveConversation() {
  const conversation = activeConversation();
  if (!conversation) return;
  conversationTitle.textContent = conversation.title;
  pageTitle.textContent = conversation.title === "New conversation" ? "How can we help today?" : conversation.title;
  messages.innerHTML = "";
  if (!conversation.messages.length) {
    messages.appendChild(renderEmptyState());
  } else {
    conversation.messages.forEach((message) => messages.appendChild(renderMessage(message)));
  }
  renderInspector();
  scrollMessages();
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
        : "";
  const article = document.createElement("article");
  article.className = `message ${message.role} ${statusClass}`.trim();
  article.dataset.messageId = message.id;
  if (message.role === "assistant") {
    article.tabIndex = 0;
    article.setAttribute("aria-label", `Copilot response: ${statusLabel(message.status)}`);
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
    const status = document.createElement("span");
    status.className = "message-status";
    status.textContent = statusLabel(message.status);
    meta.appendChild(assistantName);
    meta.appendChild(status);
  }
  const body = document.createElement("div");
  body.className = "message-body";
  renderMessageBody(body, message.message || "No response was returned.", message.citations || [], () => {
    if (message.role === "assistant") selectAssistantMessage(message.id);
  });
  article.appendChild(meta);
  article.appendChild(body);
  if (message.ticket) article.appendChild(renderTicketSummary(message.ticket));
  else if (message.category === "own_ticket" && ["error", "refused"].includes(message.status)) article.appendChild(renderTicketStatusState());
  if (message.trace?.length || message.subgraph_trace?.length) {
    article.appendChild(renderTrace(message.trace || [], message.subgraph_trace || [], message.trace_expanded !== false, (expanded) => {
      message.trace_expanded = expanded;
      saveConversations();
    }));
  }
  if (message.status === "denied") article.appendChild(renderDeniedNextStep(message));
  if (message.status === "no_answer") article.appendChild(renderNoAnswerNextStep());
  if (["error", "refused"].includes(message.status)) article.appendChild(renderRetry(message.request_text || state.lastSubmittedText, message.status === "refused" ? "Status unavailable" : "Connection issue"));
  if (message.role === "assistant" && !["error", "refused", "ready"].includes(message.status)) article.appendChild(renderFeedbackControls(message));
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
    trace_expanded: Boolean(payload.trace?.length || payload.subgraph_trace?.length),
    missing_fields: payload.missing_fields || [],
    allowed_alternatives: payload.allowed_alternatives || [],
    trace: payload.trace || [],
    conversation_id: payload.conversation_id || "web-chat",
    turn_id: payload.turn_id || "web-turn",
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
  updateCapabilityStatus(payload);
}

function collectSourceItems(payload) {
  const citations = Array.isArray(payload.citations) ? payload.citations : [];
  const sources = Array.isArray(payload.sources) ? payload.sources : [];
  return [...citations, ...sources];
}

function sanitizeTicket(ticket) {
  if (!ticket || typeof ticket !== "object") return null;
  const safe = {};
  ["ticket_id", "department", "category", "priority", "created_at", "updated_at"].forEach((field) => {
    if (ticket[field] != null && String(ticket[field]).trim()) safe[field] = String(ticket[field]).trim();
  });
  if (ticket.status != null) safe.status = safeTicketStatus(ticket.status) || "unavailable";
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
  [["ID", safeTicket.ticket_id], ["Status", safeTicket.status], ["Team", safeTicket.department], ["Category", safeTicket.category], ["Priority", safeTicket.priority], ["Updated", safeTicket.updated_at]].forEach(([label, value]) => {
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
    button.textContent = payload.feedback === rating ? "Saved" : label;
    button.addEventListener("click", () => sendFeedback(button, payload, rating));
    section.appendChild(button);
  });
  return section;
}

async function sendFeedback(button, payload, rating) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = "Saving";
  try {
    const response = await fetch("/api/feedback", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json", ...sessionHeaders() },
      body: JSON.stringify({
        conversation_id: payload.conversation_id || "web-chat",
        turn_id: payload.turn_id || "web-turn",
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
      button.textContent = "Saved";
      saveConversations();
      renderInspector();
    } else {
      button.textContent = result.message || "Could not save";
    }
  } catch (error) {
    button.textContent = "Could not save";
  } finally {
    window.setTimeout(() => {
      button.textContent = payload.feedback === rating ? "Saved" : original;
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

function closeInspector() {
  inspector.classList.remove("open");
  inspector.classList.add("is-collapsed");
  appView.classList.add("right-inspector-collapsed");
  mobileInspectorButton.setAttribute("aria-expanded", "false");
  mobileInspectorButton.setAttribute("aria-label", "Show conversation details");
  mobileInspectorButton.textContent = "Show details";
  closeInspectorButton.setAttribute("aria-label", "Expand conversation details");
  closeInspectorButton.textContent = "Show details";
  if (document.activeElement !== mobileInspectorButton && document.activeElement !== messageInput) mobileInspectorButton.focus();
}

function openInspector() {
  inspector.classList.remove("is-collapsed");
  inspector.classList.add("open");
  appView.classList.remove("right-inspector-collapsed");
  mobileInspectorButton.setAttribute("aria-expanded", "true");
  mobileInspectorButton.setAttribute("aria-label", "Hide conversation details");
  mobileInspectorButton.textContent = "Hide details";
  closeInspectorButton.setAttribute("aria-label", "Collapse conversation details");
  closeInspectorButton.textContent = "Hide details";
}

function setSidebarExpanded(expanded) {
  conversationRail.classList.toggle("is-collapsed", !expanded);
  appView.classList.toggle("left-sidebar-collapsed", !expanded);
  leftSidebarToggle.setAttribute("aria-expanded", String(expanded));
  leftSidebarToggle.setAttribute("aria-label", expanded ? "Collapse navigation" : "Expand navigation");
  leftSidebarToggle.querySelector(".sidebar-toggle-label").textContent = expanded ? "Collapse navigation" : "Expand navigation";
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
      cell.textContent = String(value);
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

function sourceMeta(item) {
  if (!item.title) return `${item.kind || "structured source"}${item.domain ? ` · ${item.domain}` : ""}`;
  const details = [item.source_type || "document"];
  if (item.page_number) details.push(`page ${item.page_number}`);
  if (item.section_heading) details.push(item.section_heading);
  if (item.updated_at) details.push(`updated ${item.updated_at}`);
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
  usernameInput.disabled = value;
  passwordInput.disabled = value;
  const label = loginButton.querySelector("span");
  if (label) label.textContent = value ? "Signing in…" : "Sign in";
}

function setSending(value) {
  state.sending = value;
  sendButton.disabled = value || !activeAccount() || !messageInput.value.trim();
  const label = sendButton.querySelector("span");
  if (label) label.textContent = value ? "Checking" : "Send";
  messageInput.disabled = value || !activeAccount();
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

async function sendMessage(text, options = {}) {
  const cleanText = String(text || "").trim();
  if (!cleanText || state.sending || !activeAccount()) return;
  if (options.addUser !== false) addUserMessage(cleanText);
  state.lastSubmittedText = cleanText;
  setSending(true);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json", ...sessionHeaders() },
      body: JSON.stringify({ message: cleanText, include_trace: traceToggle.checked }),
    });
    const payload = await response.json();
    if (response.status === 401 || response.status === 403) {
      await handleSessionExpired();
      return;
    }
    if (!response.ok) throw new Error(payload.message || `Chat request failed: ${response.status}`);
    addAssistantMessage(payload);
  } catch (error) {
    addAssistantMessage({
      status: "error",
      request_text: cleanText,
      message: error.message || "The local service did not respond. Check the server, then try again.",
    });
    setConversationStatus("The request could not be completed. You can try again.", "error");
  } finally {
    removeLoadingMessage();
    setSending(false);
    messageInput.value = "";
    updateCharacterCount();
    autoResizeComposer();
    if (activeAccount()) messageInput.focus();
  }
}

function updateResponseStatus(payload) {
  if (payload.status === "denied") {
    setConversationStatus("This request was stopped before restricted sources were searched.");
  } else if (payload.status === "error" || payload.status === "refused") {
    setConversationStatus("The request needs attention.", "error");
  } else if (payload.status === "no_answer") {
    setConversationStatus("No approved source matched that question.");
  } else {
    setConversationStatus("Answer received.");
  }
}

function updateCapabilityStatus() {
  capabilityStatus.textContent = "Access checked";
}

function setConversationStatus(text, stateName = "") {
  conversationStatus.textContent = text;
  conversationStatus.className = `conversation-status ${stateName ? `is-${stateName}` : ""}`.trim();
}

function updateCharacterCount() {
  characterCount.textContent = `${messageInput.value.length} / 2000`;
  setComposerAvailability();
}

function autoResizeComposer() {
  if (!messageInput) return;
  messageInput.style.height = "auto";
  const nextHeight = Math.min(messageInput.scrollHeight, MAX_COMPOSER_HEIGHT);
  messageInput.style.height = `${Math.max(nextHeight, 44)}px`;
  messageInput.style.overflowY = messageInput.scrollHeight > MAX_COMPOSER_HEIGHT ? "auto" : "hidden";
}

function startNewChat() {
  const conversation = createConversation();
  state.conversations.unshift(conversation);
  state.activeConversationId = conversation.id;
  state.selectedAssistantMessageId = null;
  saveConversations();
  renderConversationList();
  renderActiveConversation();
  setConversationStatus("New conversation ready.");
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

function setServiceState(text, stateName = "") {
  serviceStatus.textContent = text;
  serviceStatusIndicator.className = `status-dot ${stateName ? `is-${stateName}` : ""}`.trim();
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
  const labels = { answered: "Ready", denied: "Access limited", error: "Needs attention", refused: "Needs attention", no_answer: "No match", ready: "Ready" };
  return labels[status] || "Response";
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
mobileInspectorButton.addEventListener("click", () => {
  const expanded = mobileInspectorButton.getAttribute("aria-expanded") === "true";
  if (expanded) closeInspector();
  else openInspector();
});
closeInspectorButton.addEventListener("click", closeInspector);
chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(messageInput.value);
});
messageInput.addEventListener("input", () => {
  updateCharacterCount();
  autoResizeComposer();
});
messageInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});
suggestions.addEventListener("click", (event) => {
  const button = event.target.closest("[data-prompt]");
  if (!button || state.sending || !activeAccount()) return;
  messageInput.value = button.dataset.prompt || "";
  updateCharacterCount();
  autoResizeComposer();
  messageInput.focus();
});
document.addEventListener("click", (event) => {
  if (!accountPopover.hidden && !event.target.closest(".account-control-wrap")) closeAccountPopover();
});
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
      mobileInspectorButton.focus();
    }
  }
});
accountPopover.addEventListener("click", (event) => event.stopPropagation());

updateCharacterCount();
autoResizeComposer();
init();
