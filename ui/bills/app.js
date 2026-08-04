const $ = (s) => document.querySelector(s);
function esc(v) {
  if (v == null) return "";
  return String(v).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
let proposal = null;

async function setOperator() {
  const name = $("#operator").value.trim();
  if (name) await fetch("/bills/operator", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }) });
}

async function upload() {
  await setOperator();
  const file = $("#file").files[0];
  if (!file) { $("#status").textContent = "pick a PDF first"; return; }
  $("#status").textContent = "extracting…";
  const fd = new FormData(); fd.append("file", file);
  const res = await fetch("/bills/upload", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) { $("#status").textContent = data.detail || "upload failed"; return; }
  proposal = data; $("#status").textContent = ""; render();
}

function badge(status) { return `<span class="badge ${status}">${status}</span>`; }

function candidateSelect(cands, attr) {
  const opts = cands.map((c) => `<option value="${esc(c.chave)}">${esc(c.label)}</option>`).join("");
  return `<select class="cell" ${attr}><option value="">— pick —</option>${opts}</select>`;
}

function matchCell(m, i) {
  if (m.status === "new")
    return `${badge(m.status)} <label><input type="checkbox" data-confirm-line="${i}"> create</label>`;
  if (m.status === "ambiguous")
    return `${badge(m.status)} ${candidateSelect(m.candidates, `data-pick-line="${i}"`)}`;
  return badge(m.status);
}

function render() {
  const b = proposal.bill;
  const rows = b.lines.map((ln, i) => {
    const m = proposal.line_matches[i];
    return `<tr>
      <td><textarea class="cell desc" data-line="${i}" data-k="description" rows="1">${esc(ln.description)}</textarea></td>
      <td><input class="cell" data-line="${i}" data-k="quantity" value="${esc(ln.quantity)}"></td>
      <td><input class="cell" data-line="${i}" data-k="unit_price" value="${esc(ln.unit_price)}"></td>
      <td><input class="cell" data-line="${i}" data-k="vat_rate" value="${esc(ln.vat_rate)}"></td>
      <td><input class="cell" data-line="${i}" data-k="total" value="${esc(ln.total)}"></td>
      <td>${matchCell(m, i)}</td>
    </tr>`;
  }).join("");
  const warnings = (proposal.warnings || []).map((w) => `<li class="warn">${esc(w)}</li>`).join("");
  $("#review").innerHTML = `
    <h2>Supplier ${badge(proposal.supplier_match.status)}</h2>
    <table class="summary">
      <colgroup><col class="c-label"><col></colgroup>
      <tbody>
      <tr><th scope="row">Provider</th><td><input class="cell" data-h="supplier_name" value="${esc(b.supplier_name)}"></td></tr>
      <tr><th scope="row">NIF</th><td><input class="cell" data-h="supplier_tax_id" value="${esc(b.supplier_tax_id)}"></td></tr>
      <tr><th scope="row">Invoice #</th><td><input class="cell" data-h="number" value="${esc(b.number)}"></td></tr>
      <tr><th scope="row">Date</th><td><input class="cell" data-h="issue_date" value="${esc(b.issue_date)}"></td></tr>
      <tr><th scope="row">Total</th><td><input class="cell" data-h="gross_total" value="${esc(b.gross_total)}"></td></tr>
    </tbody></table>
    ${proposal.supplier_match.status === "new" ?
      `<label><input type="checkbox" id="confirm-supplier"> create this supplier</label>` :
      proposal.supplier_match.status === "ambiguous" ?
      candidateSelect(proposal.supplier_match.candidates, `id="pick-supplier"`) : ""}
    <table class="lines">
      <colgroup><col class="c-desc"><col class="c-num"><col class="c-num"><col class="c-num"><col class="c-num"><col class="c-match"></colgroup>
      <thead><tr><th>Description</th><th>Qty</th><th>Unit</th><th>VAT</th><th>Total</th><th>Match</th></tr></thead>
      <tbody>${rows}</tbody></table>
    <ul>${warnings}</ul>
    <button id="accept" type="button">Accept &amp; write draft</button>
    <p id="result"></p>`;
  $("#review").hidden = false;
  $("#review").querySelectorAll("textarea.desc").forEach((el) => {
    autosize(el);
    el.addEventListener("input", () => autosize(el));
  });
  $("#accept").addEventListener("click", accept);
}

function autosize(el) {
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

function collectEdits() {
  const b = proposal.bill;
  document.querySelectorAll("[data-h]").forEach((el) => { b[el.dataset.h] = el.value || null; });
  document.querySelectorAll("[data-line]").forEach((el) => {
    b.lines[+el.dataset.line][el.dataset.k] = el.value || null; });
  const cs = document.querySelector("#confirm-supplier");
  if (cs) proposal.supplier_match.confirmed = cs.checked;
  document.querySelectorAll("[data-confirm-line]").forEach((el) => {
    proposal.line_matches[+el.dataset.confirmLine].confirmed = el.checked; });
  const ps = document.querySelector("#pick-supplier");
  if (ps && ps.value) {
    proposal.supplier_match.chave = +ps.value;
    proposal.supplier_match.status = "matched";
  }
  document.querySelectorAll("[data-pick-line]").forEach((el) => {
    if (el.value) {
      const m = proposal.line_matches[+el.dataset.pickLine];
      m.chave = +el.value; m.status = "matched";
    }
  });
}

async function accept() {
  collectEdits();
  const id = proposal.proposal_id;
  const stageRes = await fetch(`/bills/stage/${id}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(proposal) });
  if (!stageRes.ok) { $("#result").textContent = "Stage failed (server error)"; return; }
  const staged = await stageRes.json();
  if (!staged.ok) {
    $("#result").innerHTML = (staged.violations || []).map((v) =>
      `<span class="warn">${esc(v.field)}: ${esc(v.message)}</span>`).join("<br>");
    return;
  }
  const commitRes = await fetch(`/bills/commit/${id}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  const out = await commitRes.json();
  $("#result").textContent = out.status === "ok"
    ? `Draft document created: Chave ${esc(out.document_chave)}`
    : `Error: ${esc(out.message)}`;
}

$("#upload-btn").addEventListener("click", upload);
