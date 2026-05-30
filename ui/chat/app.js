import { streamSse } from "./sse.js";
import { renderText } from "./renderers/text.js";
import { renderValue } from "./renderers/value.js";
import { renderTable } from "./renderers/table.js";
import { renderChart } from "./renderers/chart.js";
import { renderReport } from "./renderers/report.js";
import { initSidebar, setActiveConversation, newConversation } from "./sidebar.js";

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");

const RENDERERS = {
  text: renderText,
  value: renderValue,
  table: renderTable,
  chart: renderChart,
  report: renderReport,
};

const LAST_CONV_KEY = "lastConversationId";

// Per-conversation detached DOM containers. Switching conversations swaps
// which container is mounted in #messages, so in-flight streams keep
// mutating their own (detached) container and become visible again the
// moment the user comes back.
const conversationViews = new Map();
let currentConversationId = null;

function getView(convId) {
  let v = conversationViews.get(convId);
  if (!v) {
    const viewEl = document.createElement("div");
    viewEl.className = "conversation-view";
    v = { viewEl, loaded: false };
    conversationViews.set(convId, v);
  }
  return v;
}

function mountView(convId) {
  messagesEl.replaceChildren(getView(convId).viewEl);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function isCurrentlyViewing(convId) {
  return currentConversationId === convId;
}

function appendMsg(view, role) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  view.viewEl.appendChild(el);
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

function getSourcesContainer(parent) {
  let container = parent.querySelector(".citations");
  if (!container) {
    container = document.createElement("details");
    container.className = "citations";
    const sum = document.createElement("summary");
    sum.textContent = "Sources";
    container.appendChild(sum);
    parent.appendChild(container);
  }
  return container;
}

function appendCitation(parent, c) {
  const container = getSourcesContainer(parent);
  const item = document.createElement("div");
  item.className = "citation";
  item.textContent = `• ${c.summary}`;
  // Keep citations above the Details sub-section
  const details = container.querySelector(":scope > .steps");
  if (details) container.insertBefore(item, details);
  else container.appendChild(item);
}

function appendStep(parent, step) {
  const sources = getSourcesContainer(parent);
  let stepsEl = sources.querySelector(":scope > .steps");
  if (!stepsEl) {
    stepsEl = document.createElement("details");
    stepsEl.className = "steps";
    const sum = document.createElement("summary");
    sum.textContent = "Details";
    stepsEl.appendChild(sum);
    sources.appendChild(stepsEl);
  }
  stepsEl.appendChild(renderStep(step));
}

function renderStep(step) {
  const el = document.createElement("div");
  el.className = `step step-${step.type}`;
  if (step.type === "reasoning") {
    const body = document.createElement("div");
    body.className = "step-text";
    body.textContent = step.text;
    el.appendChild(body);
    return el;
  }
  // query step
  const sql = document.createElement("pre");
  sql.className = "step-sql";
  sql.textContent = step.sql;
  el.appendChild(sql);

  const meta = document.createElement("div");
  meta.className = "step-meta";
  if (step.error_code) {
    meta.textContent = `${step.error_code}: ${step.error_message || ""}`;
    meta.classList.add("error");
  } else {
    const parts = [`${step.row_count} row${step.row_count === 1 ? "" : "s"}`];
    if (step.duration_ms != null) parts.push(`${step.duration_ms} ms`);
    if (step.truncated) parts.push("truncated");
    meta.textContent = parts.join(" · ");
  }
  el.appendChild(meta);

  if (step.columns && step.rows_preview && step.rows_preview.length) {
    const preview = document.createElement("table");
    preview.className = "step-preview";
    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    for (const c of step.columns) {
      const th = document.createElement("th");
      th.textContent = String(c);
      headRow.appendChild(th);
    }
    thead.appendChild(headRow);
    preview.appendChild(thead);
    const tbody = document.createElement("tbody");
    for (const row of step.rows_preview) {
      const tr = document.createElement("tr");
      for (const cell of row) {
        const td = document.createElement("td");
        td.textContent = String(cell ?? "");
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    preview.appendChild(tbody);
    el.appendChild(preview);
  }
  return el;
}

function renderBlock(parent, blockData) {
  const fn = RENDERERS[blockData.kind];
  parent.appendChild(fn ? fn(blockData) : document.createTextNode(`[unsupported block: ${blockData.kind}]`));
}

function makeHandlers(asstEl, convId) {
  let lastStatus = null;
  const clearStatus = () => {
    if (lastStatus) { lastStatus.remove(); lastStatus = null; }
  };
  const scrollIfActive = () => {
    if (isCurrentlyViewing(convId)) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  };
  return {
    status(data) { clearStatus(); lastStatus = addStatus(asstEl, data.phase, data.sql || ""); scrollIfActive(); },
    block(data) { clearStatus(); renderBlock(asstEl, data); scrollIfActive(); },
    citation(data) { appendCitation(asstEl, data); scrollIfActive(); },
    step(data) { appendStep(asstEl, data); },
    error(data) { clearStatus(); addError(asstEl, data.message || "unknown"); scrollIfActive(); },
    done() { clearStatus(); scrollIfActive(); },
  };
}

async function send() {
  const text = inputEl.value.trim();
  if (!text) return;
  if (!currentConversationId) await ensureConversation();
  inputEl.value = "";

  // Capture conversation id at send time so background streams don't get
  // misrouted if the user switches away mid-flight.
  const convIdAtSend = currentConversationId;
  const view = getView(convIdAtSend);
  view.loaded = true;

  const userEl = appendMsg(view, "user");
  userEl.textContent = text;
  const asstEl = appendMsg(view, "assistant");
  if (isCurrentlyViewing(convIdAtSend)) {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  const handlers = makeHandlers(asstEl, convIdAtSend);
  try {
    for await (const ev of streamSse("/chat", {
      conversation_id: convIdAtSend,
      message: text,
    })) {
      const handler = handlers[ev.event];
      if (handler) handler(ev.data);
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
  if (isNew) {
    const v = getView(id);
    v.loaded = true;
    v.viewEl.replaceChildren();
  }
  mountView(id);
}

async function loadConversation(id) {
  // Switch the view immediately so the user sees the change.
  setCurrentConversation(id, { isNew: false });

  const v = getView(id);
  if (v.loaded) return; // already populated (and any in-flight stream is appending to it)

  try {
    const r = await fetch(`/conversations/${id}`);
    if (!r.ok) {
      if (isCurrentlyViewing(id)) {
        addError(appendMsg(v, "assistant"), "Could not load conversation.");
      }
      v.loaded = true;
      return;
    }
    const detail = await r.json();
    v.viewEl.replaceChildren();
    for (const turn of detail.turns) {
      const u = appendMsg(v, "user");
      u.textContent = turn.user_message;
      const a = appendMsg(v, "assistant");
      for (const block of turn.blocks) renderBlock(a, block);
      for (const c of turn.citations) appendCitation(a, c);
      for (const step of (turn.steps || [])) appendStep(a, step);
    }
    v.loaded = true;
    if (isCurrentlyViewing(id)) {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  } catch (e) {
    if (isCurrentlyViewing(id)) {
      addError(appendMsg(v, "assistant"), e.message);
    }
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
