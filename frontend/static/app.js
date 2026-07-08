const state = {
  profiles: [],
  activeUserId: "u001",
  sending: false,
};

const profileSelect = document.querySelector("#profileSelect");
const profileName = document.querySelector("#profileName");
const profileRole = document.querySelector("#profileRole");
const profileDepartment = document.querySelector("#profileDepartment");
const profileLocation = document.querySelector("#profileLocation");
const messages = document.querySelector("#messages");
const chatForm = document.querySelector("#chatForm");
const messageInput = document.querySelector("#messageInput");
const sendButton = document.querySelector("#sendButton");
const traceToggle = document.querySelector("#traceToggle");

async function init() {
  try {
    const response = await fetch("/api/profiles");
    const payload = await response.json();
    state.profiles = payload.profiles || [];
    renderProfiles();
  } catch (error) {
    addAssistantMessage({
      status: "error",
      message: "Could not load demo profiles. Check that the local server is running.",
    });
  }
}

function renderProfiles() {
  profileSelect.innerHTML = "";
  state.profiles.forEach((profile) => {
    const option = document.createElement("option");
    option.value = profile.user_id;
    option.textContent = `${profile.name} - ${profile.role}`;
    profileSelect.appendChild(option);
  });
  profileSelect.value = state.activeUserId;
  updateProfilePanel();
}

function updateProfilePanel() {
  const profile = activeProfile();
  if (!profile) return;
  profileName.textContent = profile.name;
  profileRole.textContent = profile.role;
  profileDepartment.textContent = profile.department;
  profileLocation.textContent = profile.location;
}

function activeProfile() {
  return state.profiles.find((profile) => profile.user_id === state.activeUserId);
}

function addUserMessage(text) {
  const article = document.createElement("article");
  article.className = "message user";
  article.innerHTML = `
    <div class="message-meta">You</div>
    <div class="message-body"></div>
  `;
  article.querySelector(".message-body").textContent = text;
  messages.appendChild(article);
  scrollMessages();
}

function addAssistantMessage(payload) {
  const article = document.createElement("article");
  const statusClass = payload.status === "denied" ? "denied" : payload.status === "error" ? "error" : "";
  article.className = `message assistant ${statusClass}`.trim();
  const meta = document.createElement("div");
  meta.className = "message-meta";
  meta.textContent = payload.status ? `Assistant - ${payload.status}` : "Assistant";
  const body = document.createElement("div");
  body.className = "message-body";
  const citations = payload.citations || [];
  renderMessageBody(body, payload.message || "No response was returned.", citations);
  article.appendChild(meta);
  article.appendChild(body);

  const sourceItems = collectSourceItems(payload);
  if (sourceItems.length) {
    article.appendChild(renderSources(sourceItems));
  }
  if (payload.trace && payload.trace.length) {
    article.appendChild(renderTrace(payload.trace));
  }
  messages.appendChild(article);
  scrollMessages();
}

function collectSourceItems(payload) {
  const citations = Array.isArray(payload.citations) ? payload.citations : [];
  const sources = Array.isArray(payload.sources) ? payload.sources : [];
  return [...citations, ...sources];
}

function renderMessageBody(container, text, citations) {
  container.textContent = "";
  const sourceIds = new Set(
    citations
      .map((citation) => Number(citation.reference_id))
      .filter((referenceId) => Number.isInteger(referenceId))
  );
  const parts = text.split(/(\[\d+\])/g);
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
      const source = document.querySelector(`#source-${referenceId}`);
      if (!source) return;
      source.scrollIntoView({ behavior: "smooth", block: "nearest" });
      source.focus({ preventScroll: true });
    });
    container.appendChild(button);
  });
}

function renderSources(items) {
  const section = document.createElement("section");
  section.className = "sources";
  const title = document.createElement("h3");
  title.textContent = "Sources";
  const list = document.createElement("div");
  list.className = "source-list";
  items.forEach((item) => {
    list.appendChild(renderSourceCard(item));
  });
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
  meta.textContent = item.title
    ? `${item.source_type || "document"} - updated ${item.updated_at || "unknown"}`
    : `${item.kind || "source"}${item.domain ? ` - ${item.domain}` : ""}`;
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

function renderTrace(trace) {
  const section = document.createElement("section");
  section.className = "trace";
  const title = document.createElement("h3");
  title.textContent = "Node trace";
  const list = document.createElement("ol");
  trace.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = `${item.node}: ${item.details.status || "running"}`;
    list.appendChild(li);
  });
  section.appendChild(title);
  section.appendChild(list);
  return section;
}

function setSending(value) {
  state.sending = value;
  sendButton.disabled = value;
  sendButton.textContent = value ? "Sending" : "Send";
}

async function sendMessage(text) {
  addUserMessage(text);
  setSending(true);
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: state.activeUserId,
        message: text,
        include_trace: traceToggle.checked,
      }),
    });
    const payload = await response.json();
    addAssistantMessage(payload);
  } catch (error) {
    addAssistantMessage({
      status: "error",
      message: "The backend did not respond. Check the local server and try again.",
    });
  } finally {
    setSending(false);
    messageInput.focus();
  }
}

function scrollMessages() {
  messages.scrollTop = messages.scrollHeight;
}

profileSelect.addEventListener("change", (event) => {
  state.activeUserId = event.target.value;
  updateProfilePanel();
});

chatForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text || state.sending) return;
  messageInput.value = "";
  sendMessage(text);
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => {
    messageInput.value = button.dataset.prompt;
    messageInput.focus();
  });
});

init();
