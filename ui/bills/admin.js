// Admin panel: draft a mapping change in prose, review the diff, apply it.
// Hidden unless the server reports the feature on AND a token is stored —
// the same two-part gate ui/chat/app.js uses for Teach/Fix.
const TOKEN_KEY = "bills_admin_token";

const panel = document.getElementById("admin-panel");
const panelBody = document.getElementById("admin-body");
const tokenInput = document.getElementById("admin-token");
const proseInput = document.getElementById("admin-prose");
const draftBtn = document.getElementById("admin-draft");
const applyBtn = document.getElementById("admin-apply");
const out = document.getElementById("admin-output");
const versionEl = document.getElementById("admin-version");
const historyEl = document.getElementById("admin-history");

let current = null;     // { version, rule, schema, history }
let proposal = null;

const token = () => localStorage.getItem(TOKEN_KEY) || "";
const headers = () => ({ "Content-Type": "application/json", "X-Admin-Token": token() });

// Both halves of the gate must hold before an operator sees anything: the
// feature is on AND this browser holds a token. `?admin=1` is the escape hatch
// for an admin on a fresh browser — it reveals the token field only, and the
// panel body stays hidden until a token is actually stored.
const escapeHatch = () => new URLSearchParams(location.search).get("admin") === "1";

async function init() {
  const r = await fetch("/admin/rules/enabled");
  if (!(await r.json()).enabled) return;
  if (!token() && !escapeHatch()) return;
  panel.hidden = false;
  tokenInput.value = token();
  panelBody.hidden = !token();
  if (token()) await refresh();
}

tokenInput.addEventListener("change", async () => {
  const v = tokenInput.value.trim();
  if (v) localStorage.setItem(TOKEN_KEY, v);
  else localStorage.removeItem(TOKEN_KEY);
  panelBody.hidden = !v;
  if (v) await refresh();
});

async function refresh() {
  const r = await fetch("/admin/rules/current", { headers: headers() });
  if (!r.ok) { out.textContent = `Cannot load rules (${r.status})`; return; }
  current = await r.json();
  versionEl.textContent = `v${current.version}`;
  historyEl.replaceChildren(...current.history.map(v => {
    const b = document.createElement("button");
    b.textContent = `revert to v${v}`;
    b.addEventListener("click", () => revert(v));
    return b;
  }));
  renderMapping();
}

function renderMapping() {
  const rows = [];
  for (const [k, f] of Object.entries(current.rule.header.fields))
    rows.push(`header.${k}: ${f.column} <- ${f.source}`);
  for (const [k, f] of Object.entries(current.rule.lines.fields))
    rows.push(`lines.${k}: ${f.column} <- ${f.source}`);
  out.textContent = rows.join("\n");
  applyBtn.hidden = true;
}

draftBtn.addEventListener("click", async () => {
  const r = await fetch("/admin/rules/draft", {
    method: "POST", headers: headers(),
    body: JSON.stringify({ prose: proseInput.value }),
  });
  const body = await r.json();
  if (!r.ok) { out.textContent = body.detail || `Draft failed (${r.status})`; return; }
  proposal = body.proposal;
  const lines = body.proposal.changes.map(c => c.action === "remove"
    ? `- remove ${c.section}.${c.name ?? c.column}`
    : `+ ${c.section}.${c.name ?? c.column} -> ${c.column}` +
      (c.source ? ` <- ${c.source}` : ""));
  if (body.violations.length) {
    out.textContent = "Rejected:\n" +
      body.violations.map(v => `  change ${v.change_index}: ${v.reason}`).join("\n");
    applyBtn.hidden = true;
    return;
  }
  out.textContent = `${body.proposal.rationale}\n\n${lines.join("\n")}`;
  applyBtn.hidden = false;
});

applyBtn.addEventListener("click", async () => {
  const r = await fetch("/admin/rules/apply", {
    method: "POST", headers: headers(),
    body: JSON.stringify({
      proposal, base_version: current.version, prose: proseInput.value,
    }),
  });
  const reply = await r.json();
  if (r.status === 409) { out.textContent = reply.detail; await refresh(); return; }
  if (!r.ok) {
    out.textContent = reply.violations
      ? reply.violations.map(v => `change ${v.change_index}: ${v.reason}`).join("\n")
      : (reply.detail || `Apply failed (${r.status})`);
    // Re-clicking would fail identically; the admin must re-draft.
    applyBtn.hidden = true;
    return;
  }
  proseInput.value = "";
  await refresh();
});

async function revert(v) {
  const r = await fetch(`/admin/rules/revert/${v}`, { method: "POST", headers: headers() });
  if (!r.ok) { out.textContent = `Revert failed (${r.status})`; return; }
  await refresh();
}

init();
