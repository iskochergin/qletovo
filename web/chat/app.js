const API_BASE = "";
const ASK_ENDPOINT = "/_api/ask";
const MANIFEST_ENDPOINT = "/manifest";

const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
const panels = {
  documents: document.getElementById("documents"),
  chat: document.getElementById("chat"),
};
const docsList = document.getElementById("docs-list");
const docsPlaceholder = document.getElementById("docs-placeholder");

const startForm = document.getElementById("start-form");
const startInput = document.getElementById("start-input");
const startSubmit = document.getElementById("start-submit");

const chatStart = document.getElementById("chat-start");
const chatFlow = document.getElementById("chat-flow");
const messagesContainer = document.getElementById("messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatSubmit = document.getElementById("chat-submit");

const toastEl = document.getElementById("toast");
const jsonModal = document.getElementById("json-modal");
const jsonRaw = document.getElementById("json-raw");
const jsonClose = document.getElementById("json-close");

let chatActive = false;
let pending = false;
let thinkingMessageEl = null;

marked.setOptions({ breaks: true, gfm: true });

async function fetchDocuments() {
  try {
    const response = await fetch(`${API_BASE}${MANIFEST_ENDPOINT}`);
    if (!response.ok) throw new Error("Не удалось получить список документов");
    const items = await response.json();
    if (!Array.isArray(items) || items.length === 0) {
      docsPlaceholder.textContent = "Документы пока не загружены.";
      return;
    }

    docsPlaceholder.classList.add("hidden");
    docsList.classList.remove("hidden");
    docsList.innerHTML = "";

    items.forEach((item) => {
      const card = document.createElement("article");
      card.className = "doc-card";

      const title = document.createElement("div");
      title.className = "doc-card-title";
      title.textContent = item.title || item.local_name || "Документ";

      const actions = document.createElement("div");
      actions.className = "doc-card-actions";

      if (item.url) {
        const link = document.createElement("a");
        link.href = item.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Открыть документ";
        if (item.page) {
          const page = document.createElement("span");
          page.textContent = ` (стр. ${item.page})`;
          link.appendChild(page);
        }
        actions.appendChild(link);
      } else {
        actions.textContent = "Ссылка недоступна";
      }

      card.append(title, actions);
      docsList.appendChild(card);
    });
  } catch (error) {
    docsPlaceholder.textContent = error.message || "Ошибка загрузки документов.";
  }
}

function switchTab(tabName) {
  tabButtons.forEach((btn) => {
    const active = btn.dataset.tab === tabName;
    btn.classList.toggle("active", active);
  });

  Object.entries(panels).forEach(([name, panel]) => {
    if (!panel) return;
    panel.classList.toggle("active", name === tabName);
  });

  if (tabName === "chat") {
    if (!chatActive) {
      startInput?.focus();
    } else {
      chatInput?.focus();
    }
  }
}

const INPUT_MAX_HEIGHT = 180;

function autoResize(textarea) {
  if (!textarea) return;
  textarea.style.height = "auto";
  const newHeight = Math.min(textarea.scrollHeight, INPUT_MAX_HEIGHT);
  textarea.style.height = `${newHeight}px`;
  textarea.style.overflowY = textarea.scrollHeight > INPUT_MAX_HEIGHT ? "auto" : "hidden";
}

function updateChatInputAlignment() {
  if (!chatInput) return;
  const shouldCenter = !chatInput.value.trim();
  chatInput.classList.toggle("centered-caret", shouldCenter);
}

function updateSubmitState() {
  if (startInput && startSubmit) {
    startSubmit.disabled = !startInput.value.trim() || pending;
  }
  if (chatInput && chatSubmit) {
    chatSubmit.disabled = !chatInput.value.trim() || pending;
  }
}

function setPending(value) {
  pending = value;

  if (chatInput && chatSubmit) {
    const hasChatText = !!chatInput.value.trim();
    chatSubmit.disabled = pending || !hasChatText;
    chatInput.disabled = pending;
  }

  if (startInput && startSubmit) {
    const hasStartText = !!startInput.value.trim();
    startSubmit.disabled = pending || !hasStartText;
    startInput.disabled = pending;
  }

  if (value && chatActive) {
    showThinkingMessage();
  } else if (!value) {
    hideThinkingMessage();
  }
}

function renderMarkdown(md) {
  const dirty = marked.parse(md || "");
  return DOMPurify.sanitize(dirty, { USE_PROFILES: { html: true } });
}

function createMessage(role, text, options = {}) {
  const { sources = [], raw, showActions = true } = options;
  const wrapper = document.createElement("div");
  wrapper.className = `message ${role}`;

  const body = document.createElement("div");
  body.className = "message-body";
  if (role === "assistant") {
    body.innerHTML = renderMarkdown(text);
  } else {
    body.textContent = text;
  }
  wrapper.appendChild(body);

  if (role === "assistant" && Array.isArray(sources) && sources.length) {
    const sourcesEl = document.createElement("div");
    sourcesEl.className = "sources";
    const title = document.createElement("div");
    title.className = "sources-title";
    title.textContent = "Документы:";
    sourcesEl.appendChild(title);

    const list = document.createElement("ul");
    sources.forEach((src) => {
      const item = document.createElement("li");
      const link = document.createElement("a");
      link.href = src.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      const page = src.page ? ` — стр. ${src.page}` : "";
      link.textContent = `${src.title || "Документ"}${page}`;
      item.appendChild(link);
      list.appendChild(item);
    });
    sourcesEl.appendChild(list);
    wrapper.appendChild(sourcesEl);
  }

  if (role === "assistant" && showActions) {
    const actions = document.createElement("div");
    actions.className = "message-actions";

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.textContent = "Копировать";
    copyBtn.addEventListener("click", () => {
      navigator.clipboard
        .writeText(text)
        .then(() => showToast("Ответ скопирован"))
        .catch(() => showToast("Не удалось скопировать", true));
    });

    const rawBtn = document.createElement("button");
    rawBtn.type = "button";
    rawBtn.textContent = "Показать сырой JSON";
    rawBtn.addEventListener("click", () => {
      if (!jsonRaw || !jsonModal) return;
      jsonRaw.textContent = JSON.stringify(raw || {}, null, 2);
      jsonModal.classList.remove("hidden");
    });

    actions.append(copyBtn, rawBtn);
    wrapper.appendChild(actions);
  }

  return wrapper;
}

function appendMessage(role, text, options) {
  if (!messagesContainer) return null;
  const autoScroll = options?.autoScroll ?? true;
  const el = createMessage(role, text, options);
  messagesContainer.appendChild(el);
  if (autoScroll) {
    messagesContainer.scrollTo({ top: messagesContainer.scrollHeight, behavior: "smooth" });
  }
  return el;
}

function showThinkingMessage() {
  if (thinkingMessageEl || !messagesContainer) return;
  thinkingMessageEl = createMessage("assistant", "Думаю…", { showActions: false });
  if (!thinkingMessageEl) return;
  thinkingMessageEl.classList.add("thinking");
  messagesContainer.appendChild(thinkingMessageEl);
}

function hideThinkingMessage() {
  if (!thinkingMessageEl) return;
  thinkingMessageEl.remove();
  thinkingMessageEl = null;
}

function scrollPromptIntoView(anchorEl) {
  if (!messagesContainer || !anchorEl) return;
  const containerRect = messagesContainer.getBoundingClientRect();
  const anchorRect = anchorEl.getBoundingClientRect();
  const offset = anchorRect.top - containerRect.top;
  const target = Math.max(messagesContainer.scrollTop + offset - 20, 0);
  messagesContainer.scrollTo({ top: target, behavior: "smooth" });
}

function enterChatMode() {
  if (chatActive) return;
  chatActive = true;
  chatStart?.classList.add("hidden");
  chatFlow?.classList.remove("hidden");
  chatInput?.focus();
}

async function sendQuestion(question) {
  enterChatMode();
  const userMessageEl = appendMessage("user", question, { autoScroll: false });
  if (chatInput) {
    chatInput.value = "";
    updateChatInputAlignment();
  }
  autoResize(chatInput);
  updateSubmitState();
  setPending(true);
  scrollPromptIntoView(userMessageEl);

  try {
    const response = await fetch(`${API_BASE}${ASK_ENDPOINT}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });

    if (!response.ok) {
      let errorMessage = "Сервис недоступен. Попробуйте позже.";
      try {
        const payload = await response.json();
        if (payload?.detail) errorMessage = payload.detail;
      } catch (err) {
        // ignore
      }
      throw new Error(errorMessage);
    }

    const data = await response.json();
    const answer = data.status === "not_found"
      ? data.answer || "Нет данных в предоставленном контексте."
      : data.answer || "";

    appendMessage("assistant", answer, {
      sources: data.sources || [],
      raw: data,
    });
  } catch (error) {
    hideThinkingMessage();
    showToast(error.message || "Ошибка запроса", true);
  } finally {
    setPending(false);
    chatInput?.focus();
  }
}

function showToast(message, isError = false) {
  if (!toastEl) return;
  toastEl.textContent = message;
  toastEl.style.background = "rgba(122, 168, 255, 0.85)";
  toastEl.classList.add("visible");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => toastEl.classList.remove("visible"), 3200);
}

function handleInput(event) {
  autoResize(event.target);
  updateSubmitState();
  if (event.target === chatInput) {
    updateChatInputAlignment();
  }
}

function handleKeydown(event, submitFn) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitFn();
  }
}

tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});

if (startInput) {
  startInput.addEventListener("input", handleInput);
  startInput.addEventListener("keydown", (event) =>
    handleKeydown(event, () => {
      if (!startInput.value.trim() || pending) return;
      startForm?.requestSubmit();
    }),
  );
}

if (chatInput) {
  chatInput.addEventListener("input", handleInput);
  chatInput.addEventListener("keydown", (event) =>
    handleKeydown(event, () => {
      if (!chatInput.value.trim() || pending) return;
      chatForm?.requestSubmit();
    }),
  );
}

if (startForm) {
  startForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = startInput?.value.trim();
    if (!question || pending) return;
    if (startInput) {
      startInput.value = "";
      autoResize(startInput);
    }
    updateSubmitState();
    switchTab("chat");
    sendQuestion(question);
  });
}

if (chatForm) {
  chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = chatInput?.value.trim();
    if (!question || pending) return;
    updateSubmitState();
    sendQuestion(question);
  });
}

if (jsonClose) {
  jsonClose.addEventListener("click", () => {
    jsonModal?.classList.add("hidden");
  });
}

if (jsonModal) {
  jsonModal.addEventListener("click", (event) => {
    if (event.target === jsonModal) jsonModal.classList.add("hidden");
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") jsonModal?.classList.add("hidden");
});

function init() {
  autoResize(startInput);
  autoResize(chatInput);
  updateChatInputAlignment();
  fetchDocuments();
  updateSubmitState();
  switchTab("chat");
}

init();
