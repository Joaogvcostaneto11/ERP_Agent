const gate = document.getElementById("operator-gate");
const appEl = document.getElementById("app");
const messages = document.getElementById("messages");
let conversationId = null;

document.getElementById("operator-go").onclick = async () => {
  const name = document.getElementById("operator-name").value.trim();
  if (!name) return;
  await fetch("/devcare/operator", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ name }),
  });
  document.getElementById("who").textContent = name;
  const r = await fetch("/devcare/conversations", { method: "POST" });
  conversationId = (await r.json()).id;
  gate.hidden = true; appEl.hidden = false;
};

function addMsg(cls, textContent) {
  const el = document.createElement("div");
  el.className = `msg ${cls}`;
  el.textContent = textContent;
  messages.appendChild(el);
  el.scrollIntoView({ block: "end" });
  return el;
}

function renderPendingChange(p) {
  const card = document.createElement("div");
  card.className = "pending-change";
  const rows = Object.entries(p.columns)
    .map(([k, v]) => `<tr><td><b>${k}</b></td><td>${v}</td></tr>`).join("");
  const target = p.target_pk != null ? ` (row ${p.target_pk})` : "";
  card.innerHTML = `
    <h4>Pending change — ${p.operation.toUpperCase()} ${p.entity}${target}</h4>
    <table>${rows || "<tr><td>(soft delete)</td></tr>"}</table>
    <div class="pc-actions">
      <button class="cancel">Cancel</button>
      <button class="confirm">Confirm write</button>
    </div>`;
  card.querySelector(".cancel").onclick = () => card.classList.add("done");
  card.querySelector(".confirm").onclick = async () => {
    const r = await fetch(`/devcare/commit/${p.change_id}`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    const res = await r.json();
    card.classList.add("done");
    if (res.status === "ok") {
      addMsg("ai", `✓ Committed ${res.operation} ${res.entity} (key ${res.primary_key}).`);
    } else {
      addMsg("error", `Commit failed: ${res.message}`);
    }
  };
  messages.appendChild(card);
  card.scrollIntoView({ block: "end" });
}

document.getElementById("composer").onsubmit = async (e) => {
  e.preventDefault();
  const input = document.getElementById("input");
  const msg = input.value.trim();
  if (!msg) return;
  addMsg("user", msg);
  input.value = "";
  const resp = await fetch("/devcare/operations", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, message: msg }),
  });
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let aiEl = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop();
    for (const part of parts) {
      const ev = part.match(/^event: (.+)$/m)?.[1];
      const dataLine = part.match(/^data: (.+)$/m)?.[1];
      if (!ev || !dataLine) continue;
      const data = JSON.parse(dataLine);
      if (ev === "block" && data.kind === "pending_change") renderPendingChange(data);
      else if (ev === "block" && data.kind === "text") aiEl = addMsg("ai", data.markdown);
      else if (ev === "error") addMsg("error", data.message || "error");
    }
  }
};
