const STORAGE_PREFIX = "nexusone.conversations.";
const SESSION_KEY = "nexusone.activeUserId";

const state = {
  profiles: [],
  activeUserId: null,
  conversations: [],
  activeConversationId: null,
  selectedAssistantMessageId: null,
  sending: false,
  lastSubmittedText: "",
  messageCount: 0,
};

const authView = document.querySelector("#authView");
const appView = document.querySelector("#appView");
const profileCards = document.querySelector("#profileCards");
const authError = document.querySelector("#authError");
const accountButton = document.querySelector("#accountButton");
const sessionRole = document.querySelector("#sessionRole");
const newChatButton = document.querySelector("#newChatButton");
const conversationList = document.querySelector("#conversationList");
const conversationTitle = document.querySelector("#conversationTitle");
const pageTitle = document.querySelector("#pageTitle");
const profileSelect = document.querySelector("#profileSelect");
const profileAvatar = document.querySelector("#profileAvatar");
const profileName = document.querySelector("#profileName");
const profileTitle = document.querySelector("#profileTitle");
const profileRole = document.querySelector("#profileRole");
const profileDepartment = document.querySelector("#profileDepartment");
const profileLocation = document.querySelector("#profileLocation");
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

async function init() {
  setConversationStatus("Loading your workspace…", "busy");
  try {
    const response = await fetch("/api/profiles");
    if (!response.ok) throw new Error(`Profile request failed: ${response.status}`);
    const payload = await response.json();
    state.profiles = Array.isArray(payload.profiles) ? payload.profiles : [];
    if (!state.profiles.length) throw new Error("No profiles were returned.");
    renderProfileCards();
    const savedUserId = window.localStorage.getItem(SESSION_KEY);
    if (savedUserId && state.profiles.some((profile) => profile.user_id === savedUserId)) {
      signIn(savedUserId);
    } else {
      setConversationStatus("Choose a demo profile to begin.");
    }
  } catch (error) {
    if (profileSelect) profileSelect.disabled = true;
    if (sendButton) sendButton.disabled = true;
    authError.textContent = "Could not load demo profiles. Check that the local server is running.";
    setConversationStatus("Workspace unavailable. Start the local server and reload.", "error");
  }
}

function renderProfileCards() {
  profileCards.innerHTML = "";
  if (profileSelect) {
    profileSelect.innerHTML = '<option value="">Choose a profile…</option>';
  }
  state.profiles.forEach((profile) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "profile-card";
    button.innerHTML = `
      <span class="profile-card-name"></span>
      <span class="profile-card-meta"></span>
      <span class="profile-card-scope"></span>
    `;
    button.querySelector(".profile-card-name").textContent = profile.name;
    button.querySelector(".profile-card-meta").textContent = `${formatRole(profile.role)} · ${formatRole(profile.department)} · ${profile.location}`;
    button.querySelector(".profile-card-scope").textContent = accessSummary(profile.role);
    button.addEventListener("click", () => signIn(profile.user_id));
    profileCards.appendChild(button);

    if (profileSelect) {
      const option = document.createElement("option");
      option.value = profile.user_id;
      option.textContent = `${profile.name} · ${formatRole(profile.role)}`;
      profileSelect.appendChild(option);
    }
  });
  if (profileSelect) profileSelect.disabled = !state.activeUserId;
}

function signIn(userId) {
  const profile = state.profiles.find((candidate) => candidate.user_id === userId);
  if (!profile || state.sending) return;
  state.activeUserId = userId;
  window.localStorage.setItem(SESSION_KEY, userId);
  state.conversations = loadConversations(userId);
  if (!state.conversations.length) {
    state.conversations.push(createConversation());
    saveConversations();
  }
  state.activeConversationId = state.conversations[0].id;
  state.selectedAssistantMessageId = latestAssistantMessage(activeConversation())?.id || null;
  resetConversation();
  authView.classList.add("hidden");
  appView.classList.remove("hidden");
  updateProfilePanel();
  renderConversationList();
  renderActiveConversation();
  setConversationStatus(`Workspace ready for ${profile.name}.`);
  setComposerAvailability();
  messageInput.focus();
}

function signOut() {
  state.activeUserId = null;
  state.conversations = [];
  state.activeConversationId = null;
  state.selectedAssistantMessageId = null;
  window.localStorage.removeItem(SESSION_KEY);
  closeInspector();
  appView.classList.add("hidden");
  authView.classList.remove("hidden");
  if (profileSelect) profileSelect.disabled = true;
  setConversationStatus("Choose a demo profile to begin.");
  const firstProfile = profileCards.querySelector("button");
  if (firstProfile) firstProfile.focus();
}

function activeProfile() {
  return state.profiles.find((profile) => profile.user_id === state.activeUserId);
}

function activeConversation() {
  return state.conversations.find((conversation) => conversation.id === state.activeConversationId);
}

function updateProfilePanel() {
  const profile = activeProfile();
  if (!profile) return;
  sessionRole.textContent = `${profile.name} - ${formatRole(profile.role)}`;
  profileName.textContent = profile.name;
  profileTitle.textContent = profile.title || "NexusOne team member";
  profileRole.textContent = formatRole(profile.role);
  profileDepartment.textContent = profile.department || "—";
  profileLocation.textContent = profile.location || "—";
  if (profileAvatar) profileAvatar.textContent = initials(profile.name);
  if (profileSelect) {
    profileSelect.value = profile.user_id;
    profileSelect.disabled = state.sending;
  }
}

function createConversation(title = "New chat") {
  const now = new Date().toISOString();
  return {
    id: `chat-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    title,
    createdAt: now,
    updatedAt: now,
    messages: [
      {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        status: "ready",
        message:
          "Ask a NexusOne question. I can answer from permitted sources, create IT/HR/Admin tickets, and explain when access is restricted.",
      },
    ],
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
  if (!state.activeUserId) return;
  window.localStorage.setItem(`${STORAGE_PREFIX}${state.activeUserId}`, JSON.stringify(state.conversations.slice(0, 30)));
}

function renderConversationList() {
  conversationList.innerHTML = "";
  state.conversations.forEach((conversation) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = conversation.id === state.activeConversationId ? "conversation-item active" : "conversation-item";
    button.innerHTML = `
      <span class="conversation-name"></span>
      <span class="conversation-meta"></span>
    `;
    button.querySelector(".conversation-name").textContent = conversation.title;
    button.querySelector(".conversation-meta").textContent = conversationMeta(conversation);
    button.addEventListener("click", () => {
      state.activeConversationId = conversation.id;
      state.selectedAssistantMessageId = latestAssistantMessage(conversation)?.id || null;
      renderConversationList();
      renderActiveConversation();
    });
    conversationList.appendChild(button);
  });
}

function renderActiveConversation() {
  const conversation = activeConversation();
  if (!conversation) return;
  conversationTitle.textContent = conversation.title;
  if (pageTitle) pageTitle.textContent = conversation.title === "New chat" ? "How can we help today?" : conversation.title;
  messages.innerHTML = "";
  conversation.messages.forEach((message) => {
    messages.appendChild(renderMessage(message));
  });
  state.messageCount = conversation.messages.length;
  renderInspector();
  scrollMessages();
}

function renderMessage(message) {
  const statusClass = message.status === "denied"
    ? "denied"
    : message.status === "error"
      ? "error"
      : message.status === "no_answer"
        ? "no-answer"
        : "";
  const article = document.createElement("article");
  article.className = `message ${message.role} ${statusClass}`.trim();
  if (message.role === "assistant") {
    article.tabIndex = 0;
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
  if (message.status === "denied") article.appendChild(renderDeniedNextStep(message));
  if (message.status === "no_answer") article.appendChild(renderNoAnswerNextStep());
  if (message.status === "error" && state.lastSubmittedText) article.appendChild(renderRetry(state.lastSubmittedText));
  if (message.role === "assistant" && !["error", "ready"].includes(message.status)) {
    article.appendChild(renderFeedbackControls(message));
  }
  return article;
}

function selectAssistantMessage(messageId) {
  state.selectedAssistantMessageId = messageId;
  renderInspector();
  messages.querySelectorAll(".message.assistant").forEach((node) => node.classList.remove("selected"));
  const conversation = activeConversation();
  if (!conversation) return;
  const index = conversation.messages.filter((message) => message.role === "assistant").findIndex((message) => message.id === messageId);
  const selected = messages.querySelectorAll(".message.assistant")[index];
  if (selected) selected.classList.add("selected");
}

function clearEmptyState() {
  document.querySelector("#emptyState")?.remove();
}

function resetConversation() {
  state.messageCount = 0;
  if (!messages) return;
  messages.innerHTML = `
    <div id="emptyState" class="empty-state">
      <div class="empty-mark" aria-hidden="true">N1</div>
      <p class="eyebrow">Start with a question</p>
      <h2>Find the answer without hunting through folders.</h2>
      <p>Ask in plain language. Copilot checks your profile first, then searches only the sources you can use.</p>
      <div class="capability-list" aria-label="Available question types">
        <div class="capability"><span class="capability-icon" aria-hidden="true">▤</span><span><strong>Policies</strong><small>Leave, expenses, remote work</small></span></div>
        <div class="capability"><span class="capability-icon" aria-hidden="true">↗</span><span><strong>Processes</strong><small>Access, onboarding, approvals</small></span></div>
        <div class="capability"><span class="capability-icon" aria-hidden="true">#</span><span><strong>Tickets</strong><small>Check your support requests</small></span></div>
      </div>
    </div>`;
}

function addUserMessage(text) {
  const conversation = activeConversation();
  if (!conversation) return;
  const message = { id: `user-${Date.now()}`, role: "user", message: text };
  conversation.messages.push(message);
  conversation.updatedAt = new Date().toISOString();
  if (conversation.title === "New chat") conversation.title = summarizeTitle(text);
  saveConversations();
  renderConversationList();
  renderActiveConversation();
}

function addLoadingMessage() {
  clearEmptyState();
  const article = document.createElement("article");
  article.id = "loadingMessage";
  article.className = "message assistant loading";
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = "Copilot";
  const body = document.createElement("div");
  body.className = "loading-body";
  body.innerHTML = '<span class="loading-dots" aria-hidden="true"><span></span><span></span><span></span></span><span>Checking access and approved sources…</span>';
  article.appendChild(meta);
  article.appendChild(body);
  messages.appendChild(article);
  scrollMessages();
}

function removeLoadingMessage() {
  document.querySelector("#loadingMessage")?.remove();
}

function addAssistantMessage(payload) {
  const conversation = activeConversation();
  if (!conversation) return;
  const statusClass = payload.status === "denied"
    ? "denied"
    : payload.status === "error"
      ? "error"
      : payload.status === "no_answer"
        ? "no-answer"
        : "";
  const message = {
    id: `assistant-${Date.now()}`,
    role: "assistant",
    status: payload.status || "answered",
    status_class: statusClass,
    reason_code: payload.reason_code,
    message: payload.message || "No response was returned.",
    citations: payload.citations || [],
    sources: payload.sources || [],
    ticket: payload.ticket || null,
    missing_fields: payload.missing_fields || [],
    allowed_alternatives: payload.allowed_alternatives || [],
    trace: payload.trace || [],
    conversation_id: payload.conversation_id || "web-chat",
    turn_id: payload.turn_id || "web-turn",
    latency_ms: payload.latency_ms,
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

function renderTicketSummary(ticket) {
  const section = document.createElement("section");
  section.className = "ticket-summary";
  const title = document.createElement("h3");
  title.textContent = "Ticket created";
  const list = document.createElement("dl");
  [["ID", ticket.ticket_id], ["Status", ticket.status], ["Team", ticket.department], ["Category", ticket.category], ["Priority", ticket.priority]].forEach(([label, value]) => {
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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_id: payload.conversation_id || "web-chat",
        turn_id: payload.turn_id || "web-turn",
        user_id: state.activeUserId,
        rating,
      }),
    });
    const result = await response.json();
    if (result.status === "stored") {
      payload.feedback = rating;
      button.textContent = "Saved";
      saveConversations();
      renderInspector();
    } else {
      button.textContent = "Failed";
    }
  } catch (error) {
    button.textContent = "Failed";
  } finally {
    setTimeout(() => {
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

function openInspector() {
  inspector.classList.add("open");
  mobileInspectorButton.setAttribute("aria-expanded", "true");
}

function closeInspector() {
  inspector.classList.remove("open");
  mobileInspectorButton.setAttribute("aria-expanded", "false");
}

function renderInspector() {
  const message = selectedAssistantMessage();
  inspectorContent.innerHTML = "";
  if (!message) {
    const empty = document.createElement("p");
    empty.className = "empty-note";
    empty.textContent = "Select an answer to inspect sources, ticket details, feedback, and trace output.";
    inspectorContent.appendChild(empty);
    return;
  }
  if (message.ticket) inspectorContent.appendChild(renderTicketSummary(message.ticket));
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
      <div><dt>Latency</dt><dd>${message.latency_ms == null ? "-" : `${message.latency_ms}ms`}</dd></div>
      <div><dt>Feedback</dt><dd>${escapeHtml(message.feedback || "Not submitted")}</dd></div>
    </dl>`;
  inspectorContent.appendChild(meta);
  if (message.trace && message.trace.length) inspectorContent.appendChild(renderTrace(message.trace));
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

function renderTrace(trace) {
  const section = document.createElement("section");
  section.className = "trace";
  const title = document.createElement("h3");
  title.textContent = "Node trace";
  const list = document.createElement("ol");
  trace.forEach((item) => {
    const li = document.createElement("li");
    const details = item.details || {};
    li.textContent = `${item.node}: ${details.status || "running"}`;
    list.appendChild(li);
  });
  section.appendChild(title);
  section.appendChild(list);
  return section;
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

function renderRetry(text) {
  const section = document.createElement("section");
  section.className = "message-next-step";
  const title = document.createElement("h3");
  title.textContent = "Connection issue";
  const retry = document.createElement("button");
  retry.type = "button";
  retry.className = "retry-button";
  retry.textContent = "Try again";
  retry.addEventListener("click", () => sendMessage(text));
  section.appendChild(title);
  section.appendChild(retry);
  return section;
}

function setSending(value) {
  state.sending = value;
  if (sendButton) {
    sendButton.disabled = value || !activeProfile() || !messageInput.value.trim();
    const label = sendButton.querySelector("span");
    if (label) label.textContent = value ? "Checking" : "Send";
  }
  messageInput.disabled = value || !activeProfile();
  if (profileSelect) profileSelect.disabled = value;
  if (value) {
    setConversationStatus("Checking access and approved sources…", "busy");
    addLoadingMessage();
  }
}

function setComposerAvailability() {
  if (!sendButton) return;
  sendButton.disabled = state.sending || !activeProfile() || !messageInput.value.trim();
  messageInput.disabled = state.sending || !activeProfile();
}

async function sendMessage(text, options = {}) {
  const cleanText = String(text || "").trim();
  if (!cleanText || state.sending || !activeProfile()) return;
  if (options.addUser !== false) addUserMessage(cleanText);
  state.lastSubmittedText = cleanText;
  setSending(true);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: state.activeUserId, message: cleanText, include_trace: traceToggle.checked }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || `Chat request failed: ${response.status}`);
    addAssistantMessage(payload);
  } catch (error) {
    addAssistantMessage({
      status: "error",
      message: "The local service did not respond. Check the server, then try again.",
    });
    setConversationStatus("The request could not be completed. You can try again.", "error");
  } finally {
    removeLoadingMessage();
    setSending(false);
    messageInput.value = "";
    updateCharacterCount();
    messageInput.focus();
  }
}

function updateResponseStatus(payload) {
  if (payload.status === "denied") {
    setConversationStatus("This request was stopped before restricted sources were searched.");
  } else if (payload.status === "error") {
    setConversationStatus("The request needs attention.", "error");
  } else if (payload.status === "no_answer") {
    setConversationStatus("No approved source matched that question.");
  } else {
    setConversationStatus("Answer ready. Review the approved sources below it.");
  }
}

function setConversationStatus(text, stateName = "") {
  if (!conversationStatus) return;
  conversationStatus.textContent = text;
  conversationStatus.className = `conversation-status ${stateName ? `is-${stateName}` : ""}`.trim();
}

function updateCharacterCount() {
  if (characterCount) characterCount.textContent = `${messageInput.value.length} / 2000`;
  setComposerAvailability();
}

function startNewChat() {
  const conversation = createConversation();
  state.conversations.unshift(conversation);
  state.activeConversationId = conversation.id;
  state.selectedAssistantMessageId = latestAssistantMessage(conversation)?.id || null;
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
  return clean.length > 44 ? `${clean.slice(0, 41)}...` : clean || "New chat";
}

function conversationMeta(conversation) {
  const count = Math.max(0, conversation.messages.length - 1);
  const date = new Date(conversation.updatedAt);
  const label = Number.isNaN(date.getTime()) ? "Saved" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return `${count} message${count === 1 ? "" : "s"} - ${label}`;
}

function accessSummary(role) {
  const summaries = {
    employee: "Public policies, own tickets, general process guidance.",
    manager: "Employee access plus manager guidance and team-oriented docs.",
    hr: "HR policies, HR queue context, and employee lifecycle docs.",
    finance: "Finance policies, budget summaries, and vendor/payment data.",
    it_admin: "IT support knowledge, device/security docs, and IT queues.",
    admin_ops: "Facilities, admin requests, and office operations.",
    executive: "Executive reports and strategy summaries except CEO-only data.",
    ceo: "Full executive scope including CEO-only material.",
  };
  return summaries[role] || "Role-scoped company access.";
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

accountButton.addEventListener("click", signOut);
newChatButton.addEventListener("click", startNewChat);
mobileInspectorButton.addEventListener("click", openInspector);
closeInspectorButton.addEventListener("click", closeInspector);
profileSelect.addEventListener("change", (event) => {
  state.activeUserId = event.target.value;
  if (state.activeUserId) signIn(state.activeUserId);
});
chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(messageInput.value);
});
messageInput.addEventListener("input", updateCharacterCount);
messageInput.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});
suggestions.addEventListener("click", (event) => {
  const button = event.target.closest("[data-prompt]");
  if (!button || state.sending) return;
  messageInput.value = button.dataset.prompt || "";
  updateCharacterCount();
  messageInput.focus();
});

updateCharacterCount();
init();
