let currentConvId = null;
let onSelect = null;
const POLL_MS = 30000;

const listEl = () => document.getElementById("conversation-list");

export function initSidebar({ onConversationSelected }) {
  onSelect = onConversationSelected;
  document.getElementById("new-chat").addEventListener("click", newConversation);
  const toggle = document.getElementById("sidebar-toggle");
  if (toggle) {
    toggle.addEventListener("click", () => {
      document.getElementById("sidebar").classList.toggle("open");
    });
  }
  refresh();
  setInterval(refresh, POLL_MS);
}

export function setActiveConversation(id) {
  currentConvId = id;
  paintActive();
}

export async function newConversation() {
  const r = await fetch("/conversations", { method: "POST" });
  const { id } = await r.json();
  currentConvId = id;
  if (onSelect) onSelect(id, { isNew: true });
  await refresh();
}

export async function refresh() {
  const r = await fetch("/conversations");
  const { conversations } = await r.json();
  render(conversations);
}

function render(conversations) {
  const el = listEl();
  el.innerHTML = "";
  if (conversations.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty-state";
    empty.textContent = "No conversations yet. Ask something to start.";
    el.appendChild(empty);
    return;
  }
  for (const c of conversations) {
    const li = document.createElement("li");
    li.dataset.id = c.id;
    if (c.id === currentConvId) li.classList.add("active");

    const title = document.createElement("div");
    title.className = "conv-title";
    title.textContent = c.title || "Untitled conversation";

    const when = document.createElement("div");
    when.className = "conv-when";
    when.textContent = relativeTime(c.updated_at);

    const del = document.createElement("button");
    del.className = "conv-delete";
    del.type = "button";
    del.textContent = "×";
    del.title = "Delete";
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Delete this conversation?")) return;
      await fetch(`/conversations/${c.id}`, { method: "DELETE" });
      if (c.id === currentConvId) {
        await newConversation();
      } else {
        await refresh();
      }
    });

    li.addEventListener("click", () => {
      if (c.id === currentConvId) return;
      currentConvId = c.id;
      if (onSelect) onSelect(c.id, { isNew: false });
      paintActive();
      document.getElementById("sidebar").classList.remove("open");
    });

    li.append(title, when, del);
    el.appendChild(li);
  }
}

function paintActive() {
  for (const li of listEl().querySelectorAll("li")) {
    li.classList.toggle("active", li.dataset.id === currentConvId);
  }
}

function relativeTime(iso) {
  try {
    const then = new Date(iso).getTime();
    const now = Date.now();
    const diff = Math.max(0, now - then);
    const s = Math.floor(diff / 1000);
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
    if (s < 172800) return "yesterday";
    if (s < 604800) return `${Math.floor(s / 86400)} d ago`;
    return new Date(iso).toLocaleDateString();
  } catch {
    return "";
  }
}
