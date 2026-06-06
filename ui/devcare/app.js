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

// Year/Month/Day dropdowns instead of a native date input, so the year is a
// type-ahead dropdown (no slow scrolling through the calendar). Exposes a
// `.value` getter returning "YYYY-MM-DD" (or "" while incomplete).
function makeDateControl(value) {
  const wrap = document.createElement("div");
  wrap.className = "date-parts";
  const mk = (placeholder, opts) => {
    const s = document.createElement("select");
    const blank = document.createElement("option");
    blank.value = ""; blank.textContent = placeholder;
    s.appendChild(blank);
    for (const o of opts) {
      const opt = document.createElement("option");
      opt.value = o.value; opt.textContent = o.label;
      s.appendChild(opt);
    }
    return s;
  };
  const now = new Date().getFullYear();
  const years = [];
  for (let y = now; y >= 1900; y--) years.push({ value: String(y), label: String(y) });
  const months = ["January", "February", "March", "April", "May", "June", "July",
                  "August", "September", "October", "November", "December"]
    .map((name, i) => ({ value: String(i + 1).padStart(2, "0"), label: name }));
  const days = [];
  for (let d = 1; d <= 31; d++) days.push({ value: String(d).padStart(2, "0"), label: String(d) });

  const y = mk("Year", years), m = mk("Month", months), d = mk("Day", days);
  if (value) {
    const [yy, mm, dd] = String(value).split("-");
    y.value = yy || ""; m.value = mm || ""; d.value = dd || "";
  }
  wrap.append(y, m, d);
  Object.defineProperty(wrap, "value", {
    get() { return (y.value && m.value && d.value) ? `${y.value}-${m.value}-${d.value}` : ""; },
  });
  return wrap;
}

function renderForm(form) {
  const card = document.createElement("div");
  card.className = "devcare-form";
  const h = document.createElement("h4");
  h.textContent = form.title;
  card.appendChild(h);

  const grid = document.createElement("div");
  grid.className = "form-grid";
  const inputs = {};
  for (const f of form.fields) {
    const row = document.createElement("label");
    row.className = "form-field";
    const cap = document.createElement("span");
    cap.className = "form-label";
    cap.textContent = f.label + (f.required ? " *" : "");
    row.appendChild(cap);

    let el;
    if (f.input === "select") {
      el = document.createElement("select");
      const blank = document.createElement("option");
      blank.value = "";
      blank.textContent = f.required ? "— choose —" : "—";
      el.appendChild(blank);
      for (const o of f.options || []) {
        const opt = document.createElement("option");
        opt.value = String(o.value);
        opt.textContent = o.label;
        if (f.value != null && String(o.value) === String(f.value)) opt.selected = true;
        el.appendChild(opt);
      }
    } else if (f.input === "date") {
      el = makeDateControl(f.value);
    } else {
      el = document.createElement("input");
      el.type = f.input; // text | number
      if (f.maxlength) el.maxLength = f.maxlength;
      if (f.step != null) el.step = String(f.step);
      if (f.value != null) el.value = f.value;
    }
    inputs[f.name] = el;
    row.appendChild(el);
    const err = document.createElement("span");
    err.className = "form-error";
    err.dataset.errFor = f.name;
    row.appendChild(err);
    grid.appendChild(row);
  }
  card.appendChild(grid);

  const actions = document.createElement("div");
  actions.className = "pc-actions";
  const cancel = document.createElement("button");
  cancel.className = "cancel";
  cancel.textContent = "Cancel";
  const review = document.createElement("button");
  review.className = "confirm";
  review.textContent = "Review";
  actions.appendChild(cancel);
  actions.appendChild(review);
  card.appendChild(actions);

  cancel.onclick = () => card.classList.add("done");

  review.onclick = async () => {
    card.querySelectorAll(".form-error").forEach((e) => (e.textContent = ""));
    const fields = {};
    for (const [name, el] of Object.entries(inputs)) {
      const v = typeof el.value === "string" ? el.value.trim() : el.value;
      if (v !== "") fields[name] = v;
    }
    const r = await fetch("/devcare/stage", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, entity: form.entity,
                             operation: form.operation, fields, target_pk: form.target_pk }),
    });
    let res = {};
    try { res = await r.json(); } catch (_) { /* empty */ }
    if (r.ok && res.ok && res.pending_change) {
      card.classList.add("done");
      renderPendingChange(res.pending_change);
    } else if (res.violations) {
      for (const v of res.violations) {
        const slot = card.querySelector(`.form-error[data-err-for="${v.field}"]`);
        if (slot) slot.textContent = v.message;
        else addMsg("error", `${v.field}: ${v.message}`);
      }
    } else {
      addMsg("error", res.error || res.message || "could not stage the record");
    }
  };

  messages.appendChild(card);
  card.scrollIntoView({ block: "end" });
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
  // Show a "being processed" indicator until the first response arrives.
  const pending = addMsg("ai processing", "Processing your request…");
  const clearPending = () => { if (pending.parentNode) pending.remove(); };
  try {
    const resp = await fetch("/devcare/operations", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ conversation_id: conversationId, message: msg }),
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
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
        if (ev === "block" || ev === "error") clearPending(); // first content arrived
        if (ev === "block" && data.kind === "pending_change") renderPendingChange(data);
        else if (ev === "block" && data.kind === "form") renderForm(data);
        else if (ev === "block" && data.kind === "text") addMsg("ai", data.markdown);
        else if (ev === "error") addMsg("error", data.message || "error");
      }
    }
  } catch (err) {
    addMsg("error", "Could not reach the server. Please try again.");
  } finally {
    clearPending();
  }
};
