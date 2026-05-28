export function renderReport(block) {
  const wrap = document.createElement("div");
  wrap.className = "report";
  const title = document.createElement("h2");
  title.textContent = block.title;
  const body = document.createElement("div");
  body.innerHTML = window.DOMPurify.sanitize(block.html || "");
  const link = document.createElement("a");
  link.href = block.pdf_url;
  link.className = "pdf-link";
  link.textContent = "Download PDF";
  link.target = "_blank";
  link.rel = "noopener";
  link.addEventListener("click", async (e) => {
    // If the server returns 501 (WeasyPrint unavailable), surface a friendly message.
    e.preventDefault();
    const r = await fetch(block.pdf_url);
    if (r.status === 501) {
      alert("PDF rendering is unavailable on this server. Use your browser's Print > Save as PDF.");
      return;
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener");
  });
  wrap.append(title, body, link);
  return wrap;
}
