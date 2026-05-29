export function renderReport(block) {
  const wrap = document.createElement("div");
  wrap.className = "report";
  const title = document.createElement("h2");
  title.textContent = block.title;
  const body = document.createElement("div");
  body.innerHTML = window.DOMPurify.sanitize(block.html || "");
  const link = document.createElement("a");
  link.href = block.view_url;
  link.className = "pdf-link";
  link.textContent = "Open report (print to PDF)";
  link.target = "_blank";
  link.rel = "noopener";
  wrap.append(title, body, link);
  return wrap;
}
