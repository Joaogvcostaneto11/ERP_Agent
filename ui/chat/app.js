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

// ── Feedback (Teach / Fix) ────────────────────────────────────────────────────
// Keyed on assistant element → array of SQL strings (from query steps)
const turnSqls = new WeakMap();

let feedbackEnabled = false;

const FEEDBACK_TOKEN_KEY = "feedback_token";

function feedbackToken() {
  return localStorage.getItem(FEEDBACK_TOKEN_KEY) || "";
}

async function initFeedback() {
  try {
    const r = await fetch("/feedback/enabled");
    if (!r.ok) return;
    const { enabled } = await r.json();
    feedbackEnabled = enabled;
    if (!feedbackEnabled) return;
    renderDevControl();
  } catch {
    // feedback endpoint absent — silently skip
  }
}

function renderDevControl() {
  const header = document.querySelector(".sidebar-header");
  if (!header || header.querySelector(".dev-unlock")) return;
  const btn = document.createElement("button");
  btn.className = "dev-unlock";
  btn.type = "button";
  btn.title = "Set dev feedback token";
  btn.textContent = "🔓 Dev";
  btn.addEventListener("click", () => {
    const tok = window.prompt("Enter feedback token:", feedbackToken());
    if (tok !== null) localStorage.setItem(FEEDBACK_TOKEN_KEY, tok.trim());
  });
  header.appendChild(btn);
}

// Called after a turn is fully rendered (both live and history replay).
// asstEl: the assistant .msg div
// userQuestion: the user's text for this turn
// turnId: server-side turn id (may be undefined)
function attachTeachButton(asstEl, userQuestion, turnId) {
  if (!feedbackEnabled || !feedbackToken()) return;
  if (asstEl.querySelector(".teach-btn")) return; // already attached
  const btn = document.createElement("button");
  btn.className = "teach-btn";
  btn.type = "button";
  btn.textContent = "Teach / Fix";
  btn.addEventListener("click", () => openTeachPanel(asstEl, userQuestion, turnId));
  asstEl.appendChild(btn);
}

function openTeachPanel(asstEl, userQuestion, turnId) {
  // Collect SQL from this turn (stored in WeakMap by makeHandlers / loadConversation)
  const sqls = turnSqls.get(asstEl) || [];
  const sqlText = sqls.join("\n\n-- next query --\n\n");

  const overlay = document.createElement("div");
  overlay.className = "teach-overlay";

  const panel = document.createElement("div");
  panel.className = "teach-panel";

  // Header
  const h = document.createElement("div");
  h.className = "teach-panel-header";
  const title = document.createElement("strong");
  title.textContent = "Teach / Fix";
  const closeBtn = document.createElement("button");
  closeBtn.className = "teach-close";
  closeBtn.type = "button";
  closeBtn.textContent = "×";
  closeBtn.addEventListener("click", () => overlay.remove());
  h.append(title, closeBtn);
  panel.appendChild(h);

  // Question (read-only display)
  const qLabel = document.createElement("label");
  qLabel.className = "teach-label";
  qLabel.textContent = "Question";
  const qEl = document.createElement("textarea");
  qEl.className = "teach-field";
  qEl.rows = 2;
  qEl.value = userQuestion;
  qEl.readOnly = true;
  panel.append(qLabel, qEl);

  // SQL (editable)
  const sqlLabel = document.createElement("label");
  sqlLabel.className = "teach-label";
  sqlLabel.textContent = "SQL";
  const sqlEl = document.createElement("textarea");
  sqlEl.className = "teach-field teach-sql";
  sqlEl.rows = 5;
  sqlEl.value = sqlText;
  panel.append(sqlLabel, sqlEl);

  // Explanation
  const expLabel = document.createElement("label");
  expLabel.className = "teach-label";
  expLabel.textContent = "Business logic explanation";
  const expEl = document.createElement("textarea");
  expEl.className = "teach-field";
  expEl.rows = 4;
  expEl.placeholder = "Explain what business rule should govern this query…";
  panel.append(expLabel, expEl);

  // Draft button
  const draftBtn = document.createElement("button");
  draftBtn.className = "teach-btn-action";
  draftBtn.type = "button";
  draftBtn.textContent = "Draft";

  // Entry result (editable)
  const entryLabel = document.createElement("label");
  entryLabel.className = "teach-label";
  entryLabel.textContent = "Drafted entry (editable)";
  const entryEl = document.createElement("textarea");
  entryEl.className = "teach-field teach-entry";
  entryEl.rows = 8;
  entryEl.placeholder = "Click Draft to generate…";

  // Status line
  const statusEl = document.createElement("div");
  statusEl.className = "teach-status";

  // Save button
  const saveBtn = document.createElement("button");
  saveBtn.className = "teach-btn-action teach-save";
  saveBtn.type = "button";
  saveBtn.textContent = "Save";

  const actions = document.createElement("div");
  actions.className = "teach-actions";
  actions.append(draftBtn, saveBtn);

  panel.append(actions, entryLabel, entryEl, statusEl);

  draftBtn.addEventListener("click", async () => {
    draftBtn.disabled = true;
    statusEl.textContent = "Drafting…";
    statusEl.className = "teach-status";
    try {
      const r = await fetch("/feedback/draft", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Feedback-Token": feedbackToken(),
        },
        body: JSON.stringify({
          question: qEl.value,
          sql: sqlEl.value,
          explanation: expEl.value,
        }),
      });
      if (!r.ok) {
        const msg = r.status === 403 ? "Invalid token (403)" : `Error ${r.status}`;
        statusEl.textContent = msg;
        statusEl.className = "teach-status teach-status-error";
        return;
      }
      const { entry } = await r.json();
      entryEl.value = entry;
      statusEl.textContent = "Draft ready — review and click Save.";
    } catch (e) {
      statusEl.textContent = `Network error: ${e.message}`;
      statusEl.className = "teach-status teach-status-error";
    } finally {
      draftBtn.disabled = false;
    }
  });

  saveBtn.addEventListener("click", async () => {
    if (!entryEl.value.trim()) {
      statusEl.textContent = "Draft an entry first.";
      statusEl.className = "teach-status teach-status-error";
      return;
    }
    saveBtn.disabled = true;
    statusEl.textContent = "Saving…";
    statusEl.className = "teach-status";
    try {
      const r = await fetch("/feedback/save", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Feedback-Token": feedbackToken(),
        },
        body: JSON.stringify({
          entry: entryEl.value,
          question: qEl.value,
          explanation: expEl.value,
          source_turn_id: turnId || "",
          conversation_id: currentConversationId || "",
        }),
      });
      if (!r.ok) {
        const msg = r.status === 403 ? "Invalid token (403)" : `Error ${r.status}`;
        statusEl.textContent = msg;
        statusEl.className = "teach-status teach-status-error";
        saveBtn.disabled = false;
        return;
      }
      const { ke_id } = await r.json();
      statusEl.textContent = `Saved ${ke_id}`;
      statusEl.className = "teach-status teach-status-ok";
      setTimeout(() => overlay.remove(), 1800);
    } catch (e) {
      statusEl.textContent = `Network error: ${e.message}`;
      statusEl.className = "teach-status teach-status-error";
      saveBtn.disabled = false;
    }
  });

  overlay.appendChild(panel);
  document.body.appendChild(overlay);
}
// ── End Feedback ──────────────────────────────────────────────────────────────

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

function formatUsage(step) {
  const fmt = (n) => Number(n || 0).toLocaleString();
  const parts = [
    `input ${fmt(step.input_tokens)}`,
    `output ${fmt(step.output_tokens)}`,
  ];
  if (step.cache_read_input_tokens) parts.push(`cache hit ${fmt(step.cache_read_input_tokens)}`);
  if (step.cache_creation_input_tokens) parts.push(`cache write ${fmt(step.cache_creation_input_tokens)}`);
  if (step.cost_usd != null) parts.push(formatCost(step.cost_usd));
  return parts.join(" · ");
}

function formatCost(usd) {
  if (usd >= 0.01) return `$${usd.toFixed(4)}`;
  // Sub-cent: show in fractional cents for readability
  return `${(usd * 100).toFixed(4)}¢`;
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
  if (step.type === "usage") {
    const body = document.createElement("div");
    body.className = "step-text";
    body.textContent = formatUsage(step);
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

// Live insertion: usage `step` events arrive before `block` events, so the
// Sources container gets appended early. Keep it pinned to the bottom by
// inserting new blocks before it.
function insertBlockBeforeSources(parent, blockData) {
  const fn = RENDERERS[blockData.kind];
  const node = fn ? fn(blockData) : document.createTextNode(`[unsupported block: ${blockData.kind}]`);
  const sources = parent.querySelector(":scope > .citations");
  if (sources) parent.insertBefore(node, sources);
  else parent.appendChild(node);
}

function makeHandlers(asstEl, convId, userQuestion, turnId) {
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
    block(data) { clearStatus(); insertBlockBeforeSources(asstEl, data); scrollIfActive(); },
    citation(data) { appendCitation(asstEl, data); scrollIfActive(); },
    step(data) {
      appendStep(asstEl, data);
      if (data.type === "query" && data.sql) {
        const sqls = turnSqls.get(asstEl) || [];
        sqls.push(data.sql);
        turnSqls.set(asstEl, sqls);
      }
    },
    error(data) { clearStatus(); addError(asstEl, data.message || "unknown"); scrollIfActive(); },
    done() {
      clearStatus();
      attachTeachButton(asstEl, userQuestion, turnId);
      scrollIfActive();
    },
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

  const handlers = makeHandlers(asstEl, convIdAtSend, text, "");
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
      const querySqls = [];
      for (const step of (turn.steps || [])) {
        appendStep(a, step);
        if (step.type === "query" && step.sql) querySqls.push(step.sql);
      }
      if (querySqls.length) turnSqls.set(a, querySqls);
      attachTeachButton(a, turn.user_message, turn.id || "");
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
  await initFeedback();
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
