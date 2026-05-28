import { streamSse } from "./sse.js";
import { renderText } from "./renderers/text.js";
import { renderValue } from "./renderers/value.js";
import { renderTable } from "./renderers/table.js";
import { renderChart } from "./renderers/chart.js";
import { renderReport } from "./renderers/report.js";

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const newChatBtn = document.getElementById("new-chat");

const RENDERERS = {
  text: renderText,
  value: renderValue,
  table: renderTable,
  chart: renderChart,
  report: renderReport,
};

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

async function send() {
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = "";
  const userEl = addMessage("user");
  userEl.textContent = text;
  const asstEl = addMessage("assistant");
  let lastStatus = null;
  try {
    for await (const ev of streamSse("/chat", { message: text })) {
      if (ev.event === "status") {
        if (lastStatus) lastStatus.remove();
        lastStatus = addStatus(asstEl, ev.data.phase, ev.data.sql || "");
      } else if (ev.event === "block") {
        if (lastStatus) { lastStatus.remove(); lastStatus = null; }
        const fn = RENDERERS[ev.data.kind];
        if (fn) asstEl.appendChild(fn(ev.data));
        else asstEl.appendChild(document.createTextNode(`[unsupported block: ${ev.data.kind}]`));
      } else if (ev.event === "citation") {
        // wired in Task 15 if needed
      } else if (ev.event === "error") {
        if (lastStatus) { lastStatus.remove(); lastStatus = null; }
        addError(asstEl, ev.data.message || "unknown");
      } else if (ev.event === "done") {
        if (lastStatus) { lastStatus.remove(); lastStatus = null; }
      }
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  } catch (e) {
    addError(asstEl, e.message);
  }
}

sendBtn.addEventListener("click", send);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
newChatBtn.addEventListener("click", async () => {
  await fetch("/chat/reset", { method: "POST" });
  messagesEl.innerHTML = "";
});

import { isAvailable, createRecognizer } from "./voice.js";

const micBtn = document.getElementById("mic");

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
  rec.addEventListener("end", () => {
    listening = false;
    micBtn.textContent = "🎙️";
  });
  rec.addEventListener("error", () => {
    listening = false;
    micBtn.textContent = "🎙️";
  });
})();
