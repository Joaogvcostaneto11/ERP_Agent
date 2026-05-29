import { streamSse } from "./sse.js";
import { renderText } from "./renderers/text.js";
import { renderValue } from "./renderers/value.js";
import { renderTable } from "./renderers/table.js";
import { renderChart } from "./renderers/chart.js";
import { renderReport } from "./renderers/report.js";
import { isAvailable, createRecognizer } from "./voice.js";
import { initSidebar, setActiveConversation, newConversation } from "./sidebar.js";

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const micBtn = document.getElementById("mic");

const RENDERERS = {
  text: renderText,
  value: renderValue,
  table: renderTable,
  chart: renderChart,
  report: renderReport,
};

const LAST_CONV_KEY = "lastConversationId";
let currentConversationId = null;

function addMessage(role) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

function addStatus(parent, phase, sql) {
  const s = document.createElement("div");
  s.className = "status";
  s.textContent = phase === "querying" ? `Running query: ${sql.slice(0, 80)}…` : "Thinking…";
  parent.appendChild(s);
  return s;
}

function addError(parent, msg) {
  const e = document.createElement("div");
  e.className = "error";
  e.textContent = `Error: ${msg}`;
  parent.appendChild(e);
}

function appendCitation(parent, c) {
  let container = parent.querySelector(".citations");
  if (!container) {
    container = document.createElement("details");
    container.className = "citations";
    const sum = document.createElement("summary");
    sum.textContent = "Sources";
    container.appendChild(sum);
    parent.appendChild(container);
  }
  const item = document.createElement("div");
  item.className = "citation";
  item.textContent = `• ${c.summary}`;
  container.appendChild(item);
}

function renderBlock(parent, blockData) {
  const fn = RENDERERS[blockData.kind];
  parent.appendChild(fn ? fn(blockData) : document.createTextNode(`[unsupported block: ${blockData.kind}]`));
}

function makeHandlers(asstEl) {
  let lastStatus = null;
  const clearStatus = () => {
    if (lastStatus) { lastStatus.remove(); lastStatus = null; }
  };
  return {
    status(data) { clearStatus(); lastStatus = addStatus(asstEl, data.phase, data.sql || ""); },
    block(data) { clearStatus(); renderBlock(asstEl, data); },
    citation(data) { appendCitation(asstEl, data); },
    error(data) { clearStatus(); addError(asstEl, data.message || "unknown"); },
    done() { clearStatus(); },
  };
}

async function send() {
  const text = inputEl.value.trim();
  if (!text) return;
  if (!currentConversationId) await ensureConversation();
  inputEl.value = "";
  const userEl = addMessage("user");
  userEl.textContent = text;
  const asstEl = addMessage("assistant");
  const handlers = makeHandlers(asstEl);
  try {
    for await (const ev of streamSse("/chat", {
      conversation_id: currentConversationId,
      message: text,
    })) {
      const handler = handlers[ev.event];
      if (handler) handler(ev.data);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  } catch (e) {
    addError(asstEl, e.message);
  }
}

async function ensureConversation() {
  if (currentConversationId) return;
  await newConversation();
}

function setCurrentConversation(id, { isNew }) {
  currentConversationId = id;
  localStorage.setItem(LAST_CONV_KEY, id);
  setActiveConversation(id);
  if (isNew) messagesEl.innerHTML = "";
}

async function loadConversation(id) {
  setCurrentConversation(id, { isNew: false });
  messagesEl.innerHTML = "";
  const r = await fetch(`/conversations/${id}`);
  if (!r.ok) {
    addError(addMessage("assistant"), "Could not load conversation.");
    return;
  }
  const detail = await r.json();
  for (const turn of detail.turns) {
    const u = addMessage("user");
    u.textContent = turn.user_message;
    const a = addMessage("assistant");
    for (const block of turn.blocks) renderBlock(a, block);
    for (const c of turn.citations) appendCitation(a, c);
  }
}

sendBtn.addEventListener("click", send);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});

initSidebar({
  onConversationSelected(id, { isNew }) {
    if (isNew) {
      setCurrentConversation(id, { isNew: true });
    } else {
      loadConversation(id);
    }
  },
});

(async function bootstrap() {
  const lastId = localStorage.getItem(LAST_CONV_KEY);
  if (lastId) {
    const r = await fetch(`/conversations/${lastId}`);
    if (r.ok) {
      await loadConversation(lastId);
      return;
    }
  }
  await newConversation();
})();

(async function setupVoice() {
  if (!isAvailable()) return;
  const cfg = await fetch("/config").then(r => r.json()).catch(() => ({ voice_lang: "pt-PT" }));
  const rec = createRecognizer(cfg.voice_lang);
  micBtn.hidden = false;
  let listening = false;
  micBtn.addEventListener("click", () => {
    if (listening) { rec.stop(); return; }
    listening = true;
    micBtn.textContent = "⏹";
    rec.start();
  });
  rec.addEventListener("result", (ev) => {
    const t = ev.results[0][0].transcript;
    inputEl.value = (inputEl.value ? inputEl.value + " " : "") + t;
  });
  rec.addEventListener("end", () => { listening = false; micBtn.textContent = "🎙️"; });
  rec.addEventListener("error", () => { listening = false; micBtn.textContent = "🎙️"; });
})();
