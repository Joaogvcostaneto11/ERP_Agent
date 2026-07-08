export function renderText(block) {
  const div = document.createElement("div");
  const html = window.marked.parse(block.markdown || "");
  div.innerHTML = window.DOMPurify.sanitize(html);
  return div;
}
