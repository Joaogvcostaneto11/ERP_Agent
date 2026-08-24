// Admin panel: draft a mapping change in prose, review the diff, apply it.
//
// sessionStorage, not localStorage: an admin token is a privileged credential
// and must not outlive the browser session. With localStorage, entering it once
// left every later visit to this origin showing the admin surface — including a
// brand-new session, and including an operator sitting down at the same
// machine. Re-entering it per session is the correct cost for a secret that
// authorises rewriting how invoices are written to the database.
const TOKEN_KEY = "bills_admin_token";

const panel = document.getElementById("admin-panel");
const panelBody = document.getElementById("admin-body");
const tokenRow = document.getElementById("admin-token-row");
const signedInRow = document.getElementById("admin-signed-in");
const signOutBtn = document.getElementById("admin-signout");
const tokenInput = document.getElementById("admin-token");
const proseInput = document.getElementById("admin-prose");
const draftBtn = document.getElementById("admin-draft");
const applyBtn = document.getElementById("admin-apply");
const out = document.getElementById("admin-output");
const mappingEl = document.getElementById("admin-mapping");
const versionEl = document.getElementById("admin-version");
const historyEl = document.getElementById("admin-history");

let current = null;     // { version, rule, schema, history }
let proposal = null;

const token = () => sessionStorage.getItem(TOKEN_KEY) || "";
const headers = () => ({ "Content-Type": "application/json", "X-Admin-Token": token() });

// `/` is the operator view and must never show the admin surface, whatever this
// browser happens to be holding. `/?admin=1` is the admin view. This is UI
// hygiene, not a security boundary — the server's token gate is that.
const adminView = () => new URLSearchParams(location.search).get("admin") === "1";

// Signed in: the token field is replaced by a sign-out control, so the secret
// is not left sitting in a form field for the rest of the session.
function setSignedIn(on) {
  tokenRow.hidden = on;
  signedInRow.hidden = !on;
  panelBody.hidden = !on;
}

async function init() {
  // One-time migration: this panel used to keep the token in localStorage, so
  // anyone who signed in before the switch still has an admin credential
  // sitting in persistent storage. Nothing reads it any more — purge it rather
  // than leave it there.
  localStorage.removeItem(TOKEN_KEY);
  if (!adminView()) return;
  const r = await fetch("/admin/rules/enabled");
  if (!(await r.json()).enabled) return;
  panel.hidden = false;
  tokenInput.value = "";        // never repopulate the secret into the DOM
  setSignedIn(!!token());
  if (token()) await refresh();
}

tokenInput.addEventListener("change", async () => {
  const v = tokenInput.value.trim();
  if (!v) return;
  sessionStorage.setItem(TOKEN_KEY, v);
  tokenInput.value = "";
  setSignedIn(true);
  await refresh();
});

signOutBtn.addEventListener("click", () => {
  sessionStorage.removeItem(TOKEN_KEY);
  // Drop every trace of the session: a later admin on this machine must not
  // inherit the previous one's mapping, diff, or history.
  current = null;
  proposal = null;
  out.textContent = "";
  mappingEl.textContent = "";
  versionEl.textContent = "";
  historyEl.replaceChildren();
  proseInput.value = "";
  applyBtn.hidden = true;
  setSignedIn(false);
});

// `message` is what the output box should say afterwards. The box reports the
// result of an action and nothing else — it used to be seeded with the current
// mapping on load, which made it look like a draft had already been produced
// before the admin had clicked anything. The mapping now lives in its own
// collapsed panel, so it is still available without pretending to be output.
async function refresh(message = "") {
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
  out.textContent = message;
  applyBtn.hidden = true;
}

function renderMapping() {
  const rows = [];
  for (const [k, f] of Object.entries(current.rule.header.fields))
    rows.push(`header.${k}: ${f.column} <- ${f.source}`);
  for (const [k, f] of Object.entries(current.rule.lines.fields))
    rows.push(`lines.${k}: ${f.column} <- ${f.source}`);
  mappingEl.textContent = rows.join("\n");
}

// Drafting calls Claude and takes seconds. Without a pending state the box
// keeps showing the previous content, so a request in flight is
// indistinguishable from a dead button — and an exception in here would
// otherwise reject silently and show nothing at all.
async function withPending(button, label, fn) {
  const previous = button.textContent;
  button.disabled = true;
  button.textContent = label;
  out.textContent = `${label}…`;
  try {
    await fn();
  } catch (e) {
    out.textContent = `${label} failed: ${e.message}`;
  } finally {
    button.disabled = false;
    button.textContent = previous;
  }
}

async function readBody(r) {
  const text = await r.text();
  try { return JSON.parse(text); } catch { return { detail: text.slice(0, 500) }; }
}

draftBtn.addEventListener("click", () => withPending(draftBtn, "Drafting", async () => {
  if (!proseInput.value.trim()) { out.textContent = "Describe the change first."; return; }
  const r = await fetch("/admin/rules/draft", {
    method: "POST", headers: headers(),
    body: JSON.stringify({ prose: proseInput.value }),
  });
  const body = await readBody(r);
  if (!r.ok) { out.textContent = body.detail || `Draft failed (${r.status})`; return; }
  proposal = body.proposal;
  const changes = body.proposal?.changes ?? [];
  if (body.violations.length) {
    out.textContent = "Rejected:\n" +
      body.violations.map(v => `  change ${v.change_index}: ${v.reason}`).join("\n");
    applyBtn.hidden = true;
    return;
  }
  if (!changes.length) {
    // The model is instructed to return an empty change list, with its reason
    // in rationale, when the request cannot be expressed against the schema.
    out.textContent = `No change proposed.\n\n${body.proposal?.rationale ?? ""}`;
    applyBtn.hidden = true;
    return;
  }
  const lines = changes.map(c => c.action === "remove"
    ? `- remove ${c.section}.${c.name ?? c.column}`
    : `+ ${c.section}.${c.name ?? c.column} -> ${c.column}` +
      (c.source ? ` <- ${c.source}` : ""));
  out.textContent = `${body.proposal.rationale}\n\n${lines.join("\n")}`;
  applyBtn.hidden = false;
}));

applyBtn.addEventListener("click", () => withPending(applyBtn, "Applying", async () => {
  const r = await fetch("/admin/rules/apply", {
    method: "POST", headers: headers(),
    body: JSON.stringify({
      proposal, base_version: current.version, prose: proseInput.value,
    }),
  });
  const reply = await readBody(r);
  if (r.status === 409) {
    await refresh(reply.detail || "The rule changed underneath you; re-draft.");
    return;
  }
  if (!r.ok) {
    out.textContent = reply.violations
      ? reply.violations.map(v => `change ${v.change_index}: ${v.reason}`).join("\n")
      : (reply.detail || `Apply failed (${r.status})`);
    // Re-clicking would fail identically; the admin must re-draft.
    applyBtn.hidden = true;
    return;
  }
  proseInput.value = "";
  await refresh(`Applied. Now at v${reply.version}.`);
}));

async function revert(v) {
  const r = await fetch(`/admin/rules/revert/${v}`, { method: "POST", headers: headers() });
  if (!r.ok) { out.textContent = `Revert failed (${r.status})`; return; }
  const reply = await readBody(r);
  // History is append-only: reverting to v3 writes a NEW version carrying v3's
  // content rather than rewinding, so say both numbers or the jump looks wrong.
  await refresh(`Reverted to v${v}. Now at v${reply.version}.`);
}

init();
