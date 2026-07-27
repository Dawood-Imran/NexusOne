const state = {
  profiles: [],
  activeUserId: "u001",
  sending: false,
  lastSubmittedText: "",
  messageCount: 0,
};

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
const sendButton = document.querySelector("#sendButton");
const traceToggle = document.querySelector("#traceToggle");
const conversationStatus = document.querySelector("#conversationStatus");
const characterCount = document.querySelector("#characterCount");

async function init() {
  setConversationStatus("Loading your workspace…", "busy");
  try {
    const response = await fetch("/api/profiles");
    if (!response.ok) throw new Error(`Profile request failed: ${response.status}`);
    const payload = await response.json();
    state.profiles = Array.isArray(payload.profiles) ? payload.profiles : [];
    if (!state.profiles.length) throw new Error("No profiles were returned.");
    renderProfiles();
    setConversationStatus("Ready when you are.");
    messageInput.focus();
  } catch (error) {
    profileSelect.disabled = true;
    sendButton.disabled = true;
    setConversationStatus("Workspace unavailable. Start the local server and reload.", "error");
    addAssistantMessage({
      status: "error",
      message: "Could not load the demo profiles. Check that the local NexusOne server is running, then reload this page.",
    });
  }
}

function renderProfiles() {
  profileSelect.innerHTML = "";
  state.profiles.forEach((profile) => {
    const option = document.createElement("option");
    option.value = profile.user_id;
    option.textContent = `${profile.name} · ${formatRole(profile.role)}`;
    profileSelect.appendChild(option);
  });
  profileSelect.disabled = false;
  profileSelect.value = state.activeUserId;
  if (!activeProfile()) {
    state.activeUserId = state.profiles[0].user_id;
    profileSelect.value = state.activeUserId;
  }
  updateProfilePanel();
  setComposerAvailability();
}

function updateProfilePanel() {
  const profile = activeProfile();
  if (!profile) return;
  profileAvatar.textContent = initials(profile.name);
  profileName.textContent = profile.name;
  profileTitle.textContent = profile.title || "NexusOne team member";
  profileRole.textContent = formatRole(profile.role);
  profileDepartment.textContent = profile.department || "—";
  profileLocation.textContent = profile.location || "—";
}

function activeProfile() {
  return state.profiles.find((profile) => profile.user_id === state.activeUserId);
}

function formatRole(role) {
  return String(role || "").replaceAll("_", " ");
}

function initials(name) {
  return String(name || "N1")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

function clearEmptyState() {
  document.querySelector("#emptyState")?.remove();
}

function addUserMessage(text) {
  clearEmptyState();
  const article = document.createElement("article");
  article.className = "message user";
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = "You";
  const body = document.createElement("div");
  body.className = "message-body";
  body.textContent = text;
  article.appendChild(meta);
  article.appendChild(body);
  messages.appendChild(article);
  state.messageCount += 1;
  scrollMessages();
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
  removeLoadingMessage();
  clearEmptyState();
  const article = document.createElement("article");
  const messageKey = state.messageCount + 1;
  const statusClass = payload.status === "denied"
    ? "denied"
    : payload.status === "error"
      ? "error"
      : payload.status === "no_answer"
        ? "no-answer"
        : "";
  article.className = `message assistant ${statusClass}`.trim();

  const meta = document.createElement("div");
  meta.className = "message-meta";
  const assistantName = document.createElement("span");
  assistantName.textContent = "Copilot";
  const status = document.createElement("span");
  status.className = "message-status";
  status.textContent = statusLabel(payload.status);
  meta.appendChild(assistantName);
  meta.appendChild(status);

  const body = document.createElement("div");
  body.className = "message-body";
  const citations = payload.citations || [];
  renderMessageBody(body, payload.message || "No response was returned.", citations, messageKey);
  article.appendChild(meta);
  article.appendChild(body);

  if (payload.status === "denied") {
    article.appendChild(renderDeniedNextStep(payload));
  }
  if (payload.status === "no_answer") {
    article.appendChild(renderNoAnswerNextStep());
  }
  if (payload.status === "error" && state.lastSubmittedText) {
    article.appendChild(renderRetry(state.lastSubmittedText));
  }

  const sourceItems = collectSourceItems(payload);
  if (sourceItems.length) {
    article.appendChild(renderSources(sourceItems, messageKey));
  }
  if (payload.trace && payload.trace.length) {
    article.appendChild(renderTrace(payload.trace));
  }
  messages.appendChild(article);
  state.messageCount += 1;
  updateResponseStatus(payload);
  scrollMessages();
}

function statusLabel(status) {
  const labels = {
    answered: "Answer",
    validated: "Checked",
    denied: "Access limited",
    no_answer: "No source found",
    error: "Needs attention",
  };
  return labels[status] || "Response";
}

function collectSourceItems(payload) {
  const citations = Array.isArray(payload.citations) ? payload.citations : [];
  const sources = Array.isArray(payload.sources) ? payload.sources : [];
  return [...citations, ...sources];
}

function renderMessageBody(container, text, citations, messageKey = "") {
  container.textContent = "";
  const sourceIds = new Set(
    citations
      .map((citation) => Number(citation.reference_id))
      .filter((referenceId) => Number.isInteger(referenceId))
  );
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
    button.addEventListener("click", () => {
      const source = document.querySelector(`#source-${messageKey}-${referenceId}`) || document.querySelector(`#source-${referenceId}`);
      if (!source) return;
      source.scrollIntoView({ behavior: "smooth", block: "nearest" });
      source.focus({ preventScroll: true });
    });
    container.appendChild(button);
  });
}

function renderSources(items, messageKey = "") {
  const section = document.createElement("section");
  section.className = "sources";
  const title = document.createElement("h3");
  title.textContent = "Approved sources";
  const list = document.createElement("div");
  list.className = "source-list";
  items.forEach((item) => {
    list.appendChild(renderSourceCard(item, messageKey));
  });
  section.appendChild(title);
  section.appendChild(list);
  return section;
}

function renderSourceCard(item, messageKey = "") {
  const card = document.createElement("article");
  card.className = "source-card";
  const referenceId = item.reference_id;
  if (referenceId) {
    card.id = `source-${messageKey}-${referenceId}`;
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
  sendButton.disabled = value || !activeProfile() || !messageInput.value.trim();
  messageInput.disabled = value;
  profileSelect.disabled = value;
  sendButton.querySelector("span").textContent = value ? "Checking" : "Send";
  if (value) {
    setConversationStatus("Checking access and approved sources…", "busy");
    addLoadingMessage();
  }
}

function setComposerAvailability() {
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
      body: JSON.stringify({
        user_id: state.activeUserId,
        message: cleanText,
        include_trace: traceToggle.checked,
      }),
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
  conversationStatus.textContent = text;
  conversationStatus.className = `conversation-status ${stateName ? `is-${stateName}` : ""}`.trim();
}

function resetConversation() {
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
  state.messageCount = 0;
}

function scrollMessages() {
  messages.scrollTop = messages.scrollHeight;
}

function updateCharacterCount() {
  characterCount.textContent = `${messageInput.value.length} / 2000`;
  setComposerAvailability();
}

profileSelect.addEventListener("change", (event) => {
  if (state.sending) return;
  state.activeUserId = event.target.value;
  updateProfilePanel();
  resetConversation();
  setConversationStatus(`Workspace switched to ${activeProfile()?.name || "the selected profile"}.`);
  messageInput.focus();
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

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    if (state.sending) return;
    messageInput.value = button.dataset.prompt || "";
    updateCharacterCount();
    messageInput.focus();
  });
});

updateCharacterCount();
init();
