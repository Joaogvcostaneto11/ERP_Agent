const PAGE_SIZE = 50;
const XLSX_CDN_URL = "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js";
const XLSX_SRI_HASH = ""; // filled in Task B2

export function renderTable(block) {
  const wrap = document.createElement("div");
  wrap.className = "table-block";

  if (block.caption) {
    const cap = document.createElement("div");
    cap.className = "table-caption";
    cap.textContent = block.caption;
    wrap.appendChild(cap);
  }

  const tableEl = document.createElement("table");
  const thead = document.createElement("thead");
  const headRow = document.createElement("tr");
  for (const col of block.columns) {
    const th = document.createElement("th");
    th.textContent = String(col);
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  tableEl.appendChild(thead);

  const tbody = document.createElement("tbody");
  tableEl.appendChild(tbody);

  const controls = document.createElement("div");
  controls.className = "table-controls";

  let page = 0;
  const totalPages = Math.max(1, Math.ceil(block.rows.length / PAGE_SIZE));

  function draw() {
    tbody.innerHTML = "";
    const start = page * PAGE_SIZE;
    const slice = block.rows.slice(start, start + PAGE_SIZE);
    for (const row of slice) {
      const tr = document.createElement("tr");
      for (const cell of row) {
        const td = document.createElement("td");
        td.textContent = String(cell ?? "");
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    const showPagination = totalPages > 1;
    const prev = `<button class="page-prev" ${page === 0 ? "disabled" : ""}>Prev</button>`;
    const indicator = `<span class="page-indicator">Page ${page + 1} of ${totalPages}</span>`;
    const next = `<button class="page-next" ${page >= totalPages - 1 ? "disabled" : ""}>Next</button>`;
    const empty = block.rows.length === 0;
    const csv = `<button class="dl-csv" ${empty ? "disabled" : ""}>CSV</button>`;
    const xlsx = `<button class="dl-xlsx" ${empty ? "disabled" : ""}>Excel</button>`;
    controls.innerHTML = (showPagination ? prev + indicator + next : "") + csv + xlsx;
  }

  controls.addEventListener("click", async (e) => {
    const t = e.target;
    if (!(t instanceof HTMLElement)) return;
    if (t.classList.contains("page-prev") && page > 0) { page--; draw(); }
    else if (t.classList.contains("page-next") && page < totalPages - 1) { page++; draw(); }
    else if (t.classList.contains("dl-csv")) { downloadCsv(block); }
    else if (t.classList.contains("dl-xlsx")) { await downloadXlsx(block); }
  });

  draw();
  wrap.append(tableEl, controls);
  return wrap;
}

function downloadCsv(block) {
  const bom = "﻿";
  const lines = [block.columns.map(csvCell).join(",")];
  for (const row of block.rows) {
    lines.push(row.map(csvCell).join(","));
  }
  const blob = new Blob([bom + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  triggerDownload(blob, filenameFor(block, "csv"));
}

function csvCell(value) {
  let s = value === null || value === undefined ? "" : String(value);
  // CSV-injection guard (OWASP): cells starting with =,+,-,@ get a leading apostrophe
  if (/^[=+\-@]/.test(s)) s = "'" + s;
  if (/[",\r\n]/.test(s)) {
    s = '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

async function downloadXlsx(block) {
  // Wired up in Task B2
  alert("Excel export is wired up in Task B2.");
}

function triggerDownload(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function filenameFor(block, ext) {
  const base = (block.caption || "table").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "table";
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const ts = `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}`;
  return `${base}-${ts}.${ext}`;
}
