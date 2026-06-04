const gate = document.getElementById("operator-gate");
const appEl = document.getElementById("app");
const messages = document.getElementById("messages");
let conversationId = null;

document.getElementById("operator-go").onclick = async () => {
  const name = document.getElementById("operator-name").value.trim();
  if (!name) return;
  const or = await fetch("/devcare/operator", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!or.ok) {
    alert("Could not register operator: " + (await or.text()));
    return;
  }
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

  // Title — Fix 1: all dynamic values via textContent
  const title = document.createElement("h4");
  const target = p.target_pk != null ? ` (row ${p.target_pk})` : "";
  title.textContent = `Pending change — ${p.operation.toUpperCase()} ${p.entity}${target}`;
  card.appendChild(title);

  // Table of column changes
  const table = document.createElement("table");
  const entries = Object.entries(p.columns);
  if (entries.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.textContent = "(soft delete)";
    tr.appendChild(td);
    table.appendChild(tr);
  } else {
    for (const [k, v] of entries) {
      const tr = document.createElement("tr");
      const tdKey = document.createElement("td");
      const b = document.createElement("b");
      b.textContent = k;
      tdKey.appendChild(b);
      const tdVal = document.createElement("td");
      tdVal.textContent = v;
      tr.appendChild(tdKey);
      tr.appendChild(tdVal);
      table.appendChild(tr);
    }
  }
  card.appendChild(table);

  // Actions
  const actions = document.createElement("div");
  actions.className = "pc-actions";
  const cancelBtn = document.createElement("button");
  cancelBtn.className = "cancel";
  cancelBtn.textContent = "Cancel";
  const confirmBtn = document.createElement("button");
  confirmBtn.className = "confirm";
  confirmBtn.textContent = "Confirm write";
  actions.appendChild(cancelBtn);
  actions.appendChild(confirmBtn);
  card.appendChild(actions);

  cancelBtn.onclick = () => card.classList.add("done");

  // Fix 2: handle commit fetch failure; Fix 3: primary_key fallback
  confirmBtn.onclick = async () => {
    const r = await fetch(`/devcare/commit/${p.change_id}`, {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId }),
    });
    let res = {};
    try { res = await r.json(); } catch (_) { /* empty on parse failure */ }
    card.classList.add("done");
    if (r.ok && res.status === "ok") {
      // Fix 3: use ?? '—' so null/absent key doesn't render "null"
      addMsg("ai", `✓ Committed ${res.operation} ${res.entity} (key ${res.primary_key ?? "—"}).`);
    } else {
      addMsg("error", `Commit failed: ${res.detail || res.message || "commit failed"}`);
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
  // Fix 5: removed dead `aiEl` variable
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
      else if (ev === "block" && data.kind === "text") addMsg("ai", data.markdown);
      else if (ev === "error") addMsg("error", data.message || "error");
    }
  }
};
