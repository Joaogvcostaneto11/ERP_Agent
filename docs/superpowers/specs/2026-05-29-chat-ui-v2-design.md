# Chat UI v2: PDF, Excel Export, History Panel — Design

**Status:** approved
**Date:** 2026-05-29
**Author:** brainstormed with @joaog
**Module:** `logic/chat/` + `ui/chat/`
**Scope:** three independent UX improvements building on the v1 chat module

## 1. Goal

Three additions to the existing conversational chat UI, ordered smallest to largest:

1. **Fix PDF export** — currently broken because WeasyPrint's native GTK runtime is not installed on Windows. Replace the server-side renderer with browser print-to-PDF.
2. **Export table results as CSV / Excel** — per-table buttons next to the existing pagination.
3. **Conversation history sidebar** — Perplexity-style left rail listing past conversations, persisted in SQLite, clickable to restore.

Each feature is independently shippable but shares one spec because they all touch the same chat UI surface and the v3 (history) implementation builds on the v1 (PDF) and v2 (export) cleanups.

## 2. Non-goals

- Authentication or multi-device sync — sessions remain cookie-keyed (cookie clear = history lost from that browser).
- Search across past conversations (defer to a future iteration).
- Sharing / public links for conversations.
- Branching or forking conversations.
- Conversation export as Markdown/PDF (PDF export remains scoped to `report` blocks only).
- Server-side openpyxl / WeasyPrint / Playwright installs.
- Conversation-level export buttons (per-table only; can revisit later).

## 3. Build order

| # | Feature | Touches | Plan complexity |
|---|---|---|---|
| 3.1 | PDF fix | `logic/chat/pdf.py`, `report.js`, `app.py`, `pyproject.toml`, [tests/chat/test_pdf.py](../../../tests/chat/test_pdf.py) | small |
| 3.2 | CSV/Excel export | `ui/chat/renderers/table.js`, `index.html` (script tag) | small |
| 3.3 | History panel + SQLite persistence | new `logic/chat/history.py`, `service.py` rewrite of `_sessions`, `app.py` new routes, `ui/chat/sidebar.js`, `app.js`, `chat.css`, `index.html`, new [tests/chat/test_history.py](../../../tests/chat/test_history.py) | large |

Implementation order matters: 3.3 removes the in-memory `_sessions: OrderedDict` from `ChatService`. Doing 3.1 and 3.2 first means each can land in isolation without entangling test fixtures.

---

## 4. Feature 3.1: PDF export fix

### 4.1 Approach

Drop server-side WeasyPrint. The "Download PDF" link in a `report` block opens a print-styled standalone HTML page in a new tab. The user invokes the browser's native print-to-PDF (Ctrl+P → "Save as PDF"). The browser handles fonts, page breaks, and PDF generation. Same approach Perplexity uses for "export answer".

### 4.2 Backend changes

- **Rename** [logic/chat/pdf.py](../../../logic/chat/pdf.py) → `logic/chat/report_store.py`. The class is renamed `PdfRenderer → ReportStore` (an LRU keyed by report id holding `{title, html}` tuples). `WeasyPrintUnavailable` exception is removed; the `_weasyprint_available` cached helper is removed. The CSS-injection parameter to the constructor is removed (the print-styled view route renders the wrapper HTML instead — no need to pre-inject CSS).
- **Replace** the route `GET /report/{report_id}/pdf` in [logic/chat/app.py](../../../logic/chat/app.py) with `GET /report/{report_id}/view` returning an HTML document:
  ```html
  <!doctype html>
  <html><head>
    <meta charset="utf-8">
    <title>{title}</title>
    <link rel="stylesheet" href="/report.css">
    <style>@media print { .print-hint { display: none; } }</style>
  </head><body>
    <div class="print-hint">Press <kbd>Ctrl</kbd>+<kbd>P</kbd> to save this report as PDF.</div>
    {html}
  </body></html>
  ```
  Title and HTML are escaped/passed through the same way as the existing PDF wrapper.
- **Remove** `weasyprint` from [pyproject.toml](../../../pyproject.toml) dependencies.
- **Update** [CLAUDE.md](../../../CLAUDE.md) to drop the WeasyPrint mention.
- **Service**: `ChatService.get_report_pdf` becomes `get_report_html(id) → (title, html_body)` returning the raw stored HTML; the route wraps it in the print-styled shell above.

### 4.3 Frontend changes

- [ui/chat/renderers/report.js](../../../ui/chat/renderers/report.js): link target changes from `block.pdf_url` to `block.view_url`. Label changes from "Download PDF" to "Open report (print to PDF)". Remove the 501-handler click listener; let the browser open the new tab naturally via `target="_blank"`.
- [logic/chat/envelope.py](../../../logic/chat/envelope.py): `ReportBlock.pdf_url` → `ReportBlock.view_url`. The model JSON contract is unchanged at the Claude boundary (`RawReportBlock` still has `title`+`html`); only the server-enriched `ReportBlock` field name changes.

### 4.4 Tests

- Rename [tests/chat/test_pdf.py](../../../tests/chat/test_pdf.py) → `test_report_store.py`. Remove the `WeasyPrintUnavailable` test. Keep LRU eviction + unique-id tests.
- [tests/chat/test_app.py](../../../tests/chat/test_app.py): replace `test_report_pdf_404_for_unknown` with `test_report_view_404_for_unknown`. Add `test_report_view_returns_html_with_title` (assert response is HTML, contains the title, has `text/html` content-type).
- Existing `test_report_block_gets_id_and_pdf_url` in [tests/chat/test_service.py](../../../tests/chat/test_service.py) → assert `view_url == "/report/{id}/view"`.

---

## 5. Feature 3.2: CSV / Excel export

### 5.1 Approach

Client-side, per-table buttons. No new server endpoints, no `openpyxl` dependency, no server-side state.

### 5.2 UI changes

In [ui/chat/renderers/table.js](../../../ui/chat/renderers/table.js), extend the existing `controls` row (currently holds `Prev` / `Next` / page indicator) with two trailing buttons: `CSV` and `Excel`. Both styled identically to the existing pagination buttons.

### 5.3 CSV generation

Hand-rolled, ~20 lines in `table.js`. RFC 4180 compliant:

- Header row: `columns.join(",")` after escaping
- Each cell: if it contains `,`, `"`, `\n`, or `\r`, wrap in double quotes and double-up any embedded `"`
- Line terminator: `\r\n` (Windows-friendly, Excel-friendly)
- BOM prefix: `﻿` so Excel-on-Windows opens UTF-8 cells correctly
- Trigger download: `new Blob([csv], {type: "text/csv;charset=utf-8"})`, `URL.createObjectURL`, programmatic `<a>` click, revoke after.

### 5.4 Excel generation

Lazy-load [SheetJS Community Edition](https://github.com/SheetJS/sheetjs) from a CDN on first Excel click — paid in download bytes only when needed. Use Subresource Integrity (`integrity` + `crossorigin`) consistent with the existing Plotly/DOMPurify CDN script tags in [ui/chat/index.html](../../../ui/chat/index.html).

```js
// in table.js, on first Excel click
if (!window.XLSX) await loadScript(XLSX_CDN_URL, XLSX_SRI_HASH);
const ws = XLSX.utils.aoa_to_sheet([columns, ...rows]);
const wb = XLSX.utils.book_new();
XLSX.utils.book_append_sheet(wb, ws, sheetName);
XLSX.writeFile(wb, filename);
```

`XLSX_CDN_URL` and `XLSX_SRI_HASH` are module-level constants. Pinned version: SheetJS Community Edition 0.18.5 (latest at spec time). The SRI hash is computed during implementation via `openssl dgst -sha384 -binary xlsx.full.min.js | openssl base64 -A` and committed alongside the URL.

### 5.5 Filename

`{slug(caption || "table")}-{YYYYMMDD-HHmm}.{csv|xlsx}` — `slug` strips path-unsafe chars and lowercases. Timestamps use the browser's local time.

### 5.6 Edge cases

- **Empty tables** (`rows.length === 0`): both buttons rendered `disabled`.
- **Non-ASCII data**: CSV uses UTF-8 with BOM; XLSX is UTF-8 natively.
- **Very wide tables**: no scrubbing — CSV writes all columns, XLSX writes all columns, Excel opens cleanly up to the 1000-row `ROW_CAP`.
- **Cells with embedded objects / nulls**: rendered as `String(cell ?? "")` — same as current cell display logic.

### 5.7 Tests

JS unit tests are not part of this project's setup; we rely on manual smoke. Backend has nothing to test (no server changes). The implementation plan will include a manual test checklist:

- export a 100-row table to CSV → open in Excel → columns intact, special chars preserved
- export same table to XLSX → open in Excel → columns intact
- export a table with commas/quotes/newlines in cells → reopen → data round-trips
- export an empty table → buttons disabled

---

## 6. Feature 3.3: History panel + SQLite persistence

### 6.1 Approach

Add a left sidebar listing past conversations, persisted in `logs/chat_history.sqlite`. SQLite is the source of truth — `ChatService` no longer keeps any in-memory transcript. The existing session cookie identifies who owns which conversations.

### 6.2 Schema

```sql
CREATE TABLE conversation (
  id           TEXT PRIMARY KEY,           -- 'c_' + 12 hex chars
  session_id   TEXT NOT NULL,              -- cookie value
  title        TEXT NOT NULL DEFAULT '',
  created_at   TEXT NOT NULL,              -- ISO-8601 UTC
  updated_at   TEXT NOT NULL
);
CREATE INDEX ix_conv_session ON conversation(session_id, updated_at DESC);

CREATE TABLE turn (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
  user_message    TEXT NOT NULL,
  blocks_json     TEXT NOT NULL,           -- rendered ClientBlock list as JSON
  citations_json  TEXT NOT NULL,           -- Citation list as JSON
  raw_transcript  TEXT NOT NULL,           -- Anthropic messages list snapshot AFTER this turn
  ts              TEXT NOT NULL
);
CREATE INDEX ix_turn_conv ON turn(conversation_id, id);

CREATE TABLE schema_version (
  version  INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);
```

`schema_version` is empty at v1 — the table exists so future migrations can record applied versions without an additional `CREATE TABLE` race. `CREATE TABLE IF NOT EXISTS` runs at every `HistoryStore` instantiation.

Storing **both** `blocks_json` (rendered output) **and** `raw_transcript` (Anthropic message list):

- `blocks_json` is replayed verbatim when a user clicks an old conversation — no Claude call needed for restore.
- `raw_transcript` is what Claude sees when the user continues an old conversation — so context is preserved across restores.

### 6.3 New module: `logic/chat/history.py`

```python
class HistoryStore:
    def __init__(self, path: Path) -> None: ...
    def create_conversation(self, session_id: str) -> str: ...
    def list_conversations(self, session_id: str, limit: int = 50) -> list[ConversationSummary]: ...
    def get_conversation(self, conversation_id: str, session_id: str) -> ConversationDetail | None: ...
    def delete_conversation(self, conversation_id: str, session_id: str) -> bool: ...
    def append_turn(
        self,
        conversation_id: str,
        user_message: str,
        blocks: list[dict],
        citations: list[dict],
        raw_transcript: list[dict],
    ) -> None: ...
    def update_title(self, conversation_id: str, session_id: str, title: str) -> None: ...
    def get_transcript(self, conversation_id: str, session_id: str) -> list[dict]: ...
```

- `session_id` is enforced on every read/delete/update — a cookie can only see its own conversations. Cross-session access returns `None` / `False`, never raises.
- SQLite connection: `sqlite3.connect(path, check_same_thread=False)` plus a `threading.Lock` around all writes (FastAPI runs handlers on a thread pool). Read concurrency relies on `PRAGMA journal_mode=WAL` set at init.
- All timestamps generated via `AuditLog.now_iso()` (already exists) for consistency.
- `get_transcript` returns `[]` when no turns exist (new conversation case) and the last turn's `raw_transcript` otherwise.
- Per-conversation transcript cap: `append_turn` trims `raw_transcript` to the last 40 messages before persisting (prevents unbounded growth on long conversations).

### 6.4 `ChatService` changes

- Remove `self._sessions: OrderedDict[str, list[dict]]` and all related methods (`_get_or_create_history`, `_cap_history`, `history`, `reset`).
- Constructor gains `history: HistoryStore` parameter and renames `pdf_renderer` → `report_store` per §4.2.
- `stream_turn(session_id, user_message)` → `stream_turn(conversation_id, session_id, user_message)`. At start of turn: `transcript = self._history.get_transcript(conversation_id, session_id)`. At end of a successful turn: collect the emitted `block` event payloads and the citations, then `self._history.append_turn(conversation_id, user_message, blocks, citations, transcript_after)`.
- Drop `MAX_SESSIONS` and `MAX_HISTORY_MESSAGES` constants from `service.py` — trimming lives in `HistoryStore.append_turn` (§6.3).
- The `reset` semantics change: there's no "reset". To start fresh, the frontend creates a new conversation via `POST /conversations`. The old `/chat/reset` endpoint is removed.
- Title generation: when `append_turn` is called for a conversation whose `title` is empty AND this is the first turn, fire-and-forget an `asyncio.create_task` that calls Claude Haiku 4.5 with `"Summarize this conversation in 5-7 words: USER: {user_msg} ASSISTANT: {first_block_text}"`, then `history.update_title(...)`. If the task fails, title stays empty (sidebar falls back to truncated user message).

### 6.5 New / changed endpoints

| Method | Path | Body / Params | Returns |
|---|---|---|---|
| `GET` | `/conversations` | — (uses cookie) | `{conversations: [{id, title, updated_at}], ...}` |
| `POST` | `/conversations` | — (uses cookie) | `{id}` |
| `GET` | `/conversations/{id}` | — | `{id, title, turns: [{user_message, blocks, citations, ts}]}` or 404 |
| `DELETE` | `/conversations/{id}` | — | `204 No Content` or 404 |
| `POST` | `/chat` | `{conversation_id, message}` | SSE stream (same envelope as before) |
| ~~`POST /chat/reset`~~ | — | — | **removed** |
| `GET` | `/report/{id}/view` | — | HTML (replaces the old PDF route) |

All `/conversations*` routes enforce session ownership via the `chat_session` cookie — a request with a different cookie sees a 404 for someone else's conversation id, never their data.

If `/chat` is called with an unknown or unauthorised `conversation_id`, the SSE stream emits a single `error` event with code `"unauthorized"` then `done` — no internal server error.

### 6.6 Frontend changes

**Layout** ([ui/chat/index.html](../../../ui/chat/index.html), [ui/chat/chat.css](../../../ui/chat/chat.css)):

```
┌─────────────────┬──────────────────────────────┐
│ 🗨️ ERP Chat     │                              │
│ + New chat      │   messages area              │
│ ─────────────   │                              │
│ • Conv title 1  │                              │
│   2 hours ago   │                              │
│ • Conv title 2  │                              │
│   Yesterday     │                              │
│ ...             │                              │
│                 │ ──────────────────────────── │
│                 │ [input] [🎙️] [send]          │
└─────────────────┴──────────────────────────────┘
```

- Sidebar fixed 280px wide on desktop; CSS Grid layout (`grid-template-columns: 280px 1fr`).
- Mobile (`@media (max-width: 720px)`): sidebar slides in from the left on hamburger toggle, overlays the chat area.
- Conversation row: title (or truncated first user message if title empty), relative timestamp (`"2 hours ago"`), hover reveals a small `×` delete button.
- Active conversation row highlighted (background tint).
- Empty state: "No conversations yet. Ask something to start."

**New module** [ui/chat/sidebar.js](../../../ui/chat/sidebar.js):

- `renderSidebar()` → fetches `/conversations`, renders the list
- `selectConversation(id)` → fetches `/conversations/{id}`, calls `replayConversation(detail)` from `app.js` to render past blocks
- `newConversation()` → POSTs `/conversations`, gets id, calls `selectConversation(id)`, clears the message area
- `deleteConversation(id)` → DELETEs, removes the row from the DOM, if it was active → calls `newConversation()`
- Polls `renderSidebar()` on a 30s interval to pick up title updates from the Haiku call (no SSE for sidebar — polling is fine at this cadence)

**`app.js` changes**:

- `currentConversationId` module-level variable; initialised from `localStorage.lastConversationId` on load, or via `newConversation()` if none exists.
- `send()` posts `{conversation_id: currentConversationId, message: text}` to `/chat`.
- New `replayConversation(detail)`: clears `messagesEl`, iterates `detail.turns`, for each turn appends a user message div and an assistant message div, then iterates `turn.blocks` and dispatches to `RENDERERS[block.kind]`, then iterates `turn.citations` calling `appendCitation`.
- "New chat" button moves into the sidebar; its handler calls `newConversation()`.
- `localStorage.lastConversationId = currentConversationId` on every change so refresh stays put.

**Relative timestamp**: small helper `relativeTime(iso)` rendering `"just now"`, `"5 minutes ago"`, `"2 hours ago"`, `"Yesterday"`, `"3 days ago"`, `"Jan 15"`. Updated when sidebar re-renders (every 30s + on activity).

### 6.7 Title generation

After `HistoryStore.append_turn`, if this is the conversation's first turn AND the title is empty, `ChatService` schedules a background task:

```python
asyncio.create_task(self._generate_title(conversation_id, session_id, user_message, assistant_preview))
```

`assistant_preview` is derived from the rendered blocks: the first `text` block's `markdown`, or — if no text block — a one-line synthesised summary of the first non-text block (e.g. `"Value: <label> = <value>"` or `"Table with N rows and M columns"`).

```python
async def _generate_title(...):
    try:
        resp = await self._anthropic.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=30,
            messages=[{"role": "user", "content": (
                f"Summarise this exchange as a 5-7 word title. No quotes, no punctuation at the end.\n\n"
                f"USER: {user_message[:500]}\n"
                f"ASSISTANT: {assistant_preview[:500]}"
            )}],
        )
        title = resp.content[0].text.strip()[:80]
        self._history.update_title(conversation_id, session_id, title)
    except Exception:
        logging.getLogger(__name__).exception("title generation failed")
```

Fire-and-forget — the user doesn't wait for it. If the task fails (rate limit, network), the title stays empty and the sidebar falls back to the truncated user message preview. The sidebar's 30s poll picks up the title once it lands.

### 6.8 Tests

**`tests/chat/test_history.py`** (new):

- `test_create_returns_unique_id` — two creates give different `c_` ids
- `test_list_returns_session_scoped_only` — alice's create not visible to bob's list
- `test_get_returns_none_for_other_session` — bob can't read alice's conversation by id
- `test_delete_session_isolated` — bob can't delete alice's conversation
- `test_list_orders_by_updated_at_desc` — recent first
- `test_append_turn_updates_conversation_updated_at` — touching a conversation bumps it to the top
- `test_get_transcript_returns_last_raw_transcript` — Claude continuation works
- `test_cascade_delete_removes_turns` — DELETE on conversation cleans up turns

**`tests/chat/test_service.py`** updates:

- All existing tests gain an in-memory `HistoryStore(":memory:")` fixture and pass a `conversation_id` to `stream_turn`.
- Drop `test_reset_clears_history`, `test_reset_without_session_clears_all`, `test_sessions_are_isolated` (semantics moved to history tests).
- New `test_continues_conversation_from_persisted_transcript` — append a turn manually via the store, run `stream_turn` on that conversation, assert Claude saw the prior context in `messages`.
- New `test_title_generation_fires_after_first_turn` — Haiku mock returns "A test title", assert `history.update_title` was called.

**`tests/chat/test_app.py`** updates:

- All `/conversations` CRUD tested
- Cross-session isolation: create with cookie A, attempt to read/delete with cookie B → 404
- `/chat` requires `conversation_id`; missing → 400
- `/chat` with unknown/unauthorised `conversation_id` → SSE stream with single `error` event, code `"unauthorized"`
- Remove `test_chat_reset`

### 6.9 Migration path

Old code stored history in-memory. There's nothing to migrate — any in-flight conversation in a long-running server is lost on deploy. Documented in CHANGELOG (one-line note).

---

## 7. Cross-cutting concerns

### 7.1 Security

- **Session ownership** on every `/conversations*` and `/report/{id}/view` request — a cookie value can only access its own conversations and its own reports.
- **HTML escaping** in the report view page: title escaped via existing pattern; HTML body is what Claude produced (already sanitised through `DOMPurify` on the chat side — but the print view runs DOMPurify too, since it's an isolated page).
- **CSV injection** (Excel formula execution): cells starting with `=`, `+`, `-`, `@` get a leading apostrophe (`'`) prefix when serialising to CSV/XLSX, per [OWASP CSV injection guidance](https://owasp.org/www-community/attacks/CSV_Injection).

### 7.2 Performance

- SQLite is fast enough for this scale (single-user, sub-100-conversation expected workload). No connection pool needed — a single connection with `check_same_thread=False` + a lock around writes.
- Sidebar list capped at 50 most recent conversations. Older ones remain in SQLite but aren't shown (search/pagination is a v3 concern).
- `XLSX.full.min.js` is ~600KB — only loaded on first Excel click, cached thereafter.
- Title generation runs as a background task; chat response is not blocked on it.

### 7.3 Observability

- Existing JSONL audit log gains a `conversation_id` field per row.
- `HistoryStore` failures log via `logging` but don't break the chat — if SQLite is unwritable, the conversation continues in-memory for that turn and the failure is logged once (warning, not error).

### 7.4 Backwards compatibility

- `/chat/reset` removed. Frontend code no longer calls it.
- `/report/{id}/pdf` removed, replaced by `/report/{id}/view`. No external consumers documented.
- `ReportBlock.pdf_url` → `view_url` is a Claude-side envelope shape change; the prompt does not advertise this field (it's filled in server-side), so no prompt update needed.

---

## 8. Open questions for the implementation plan

(None for this spec — these have been resolved during brainstorming.)

## 9. Acceptance checklist

When implementation is complete, the following must all hold:

- [ ] `/report/{id}/view` returns a styled HTML page; user can Ctrl+P to save as PDF
- [ ] WeasyPrint removed from `pyproject.toml`; no references to it in the codebase
- [ ] Every `table` block in the UI has working CSV and Excel download buttons
- [ ] CSV opens cleanly in Excel-on-Windows with correct accents and special chars
- [ ] XLSX preserves column types reasonably (numbers as numbers, strings as strings)
- [ ] Left sidebar lists conversations, click loads, hover shows delete, delete removes
- [ ] Refreshing the browser restores the last active conversation
- [ ] A second browser (different cookie) sees no conversations
- [ ] Titles appear in the sidebar within ~3s of the first assistant reply (Haiku)
- [ ] All existing chat tests pass with the new history fixture
- [ ] New `test_history.py` passes
- [ ] Full pytest run is green
