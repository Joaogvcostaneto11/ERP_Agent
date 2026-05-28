const PAGE_SIZE = 50;

export function renderTable(block) {
  const wrap = document.createElement("div");
  let page = 0;

  const caption = block.caption ? `<div class="status">${escapeHtml(block.caption)}</div>` : "";
  const tableEl = document.createElement("table");
  const controls = document.createElement("div");
  controls.className = "copy-csv";

  function draw() {
    const start = page * PAGE_SIZE;
    const end = Math.min(start + PAGE_SIZE, block.rows.length);
    const head = "<thead><tr>" + block.columns.map(c => `<th>${escapeHtml(c)}</th>`).join("") + "</tr></thead>";
    const body = "<tbody>" + block.rows.slice(start, end).map(row =>
      "<tr>" + row.map(cell => `<td>${escapeHtml(String(cell ?? ""))}</td>`).join("") + "</tr>"
    ).join("") + "</tbody>";
    tableEl.innerHTML = head + body;
    controls.innerHTML = `Showing ${start + 1}–${end} of ${block.rows.length}
      ${start > 0 ? '<button data-act="prev">Prev</button>' : ""}
      ${end < block.rows.length ? '<button data-act="next">Next</button>' : ""}
      <button data-act="csv">Copy CSV</button>`;
  }

  controls.addEventListener("click", (e) => {
    const act = e.target.dataset?.act;
    if (act === "prev") { page = Math.max(0, page - 1); draw(); }
    else if (act === "next") { page += 1; draw(); }
    else if (act === "csv") { copyCsv(block); }
  });

  wrap.innerHTML = caption;
  wrap.append(tableEl, controls);
  draw();
  return wrap;
}

function copyCsv(block) {
  const esc = (v) => {
    const s = String(v ?? "");
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [block.columns, ...block.rows].map(row => row.map(esc).join(",")).join("\n");
  navigator.clipboard.writeText(csv);
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}
