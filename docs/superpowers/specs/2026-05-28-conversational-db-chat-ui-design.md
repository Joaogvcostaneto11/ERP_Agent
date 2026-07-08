# Conversational DB Chat UI — Design

**Status:** approved
**Date:** 2026-05-28
**Author:** brainstormed with @joaog
**Module:** `logic/chat/` + `ui/chat/`
**Scope:** v1, single session, single user, read-only

## 1. Goal

Allow a single user to converse with the ERP database — by voice or text — and receive answers in whichever shape fits the question: a single value, a data table, a chart, a written report, or a combination. The agent generates SQL against the existing ForumSI/dbSoft database; the UI surfaces results as typed blocks.

This is the first slice of the "Adaptive UI Layer" described in [CLAUDE.md](../../../CLAUDE.md). It does not perform any business-logic mutations and does not touch the payroll engine.

## 2. Non-goals (v1)

- Multi-user, authentication, or per-user session state.
- Persistent chat history across server restarts.
- Cross-database queries (one database per process, chosen via `DATABASE_URL`).
- Any write operation (INSERT/UPDATE/DELETE/DDL).
- Streaming text token-by-token (we stream **blocks**, not characters).
- File uploads, attachments, or image input.
- Mobile-specific UI polish.

## 3. User experience

A single-page web app served from `http://localhost:8000/`:

- A vertically scrolling message list at the top.
- A bottom input area: text field + microphone button + send button.
- A "New chat" button that resets the conversation.

**Typing flow:** user types, presses Enter or clicks send, the assistant reply streams in as one or more blocks.

**Voice flow:** user holds (or toggles) the mic; the browser uses the Web Speech API (`SpeechRecognition`) to transcribe in Portuguese or English (configurable). On stop, the transcript fills the text field; the user can edit before sending or have it auto-send. If `SpeechRecognition` is unavailable (e.g., Firefox) the mic button is hidden — text input continues to work.

**Answer shapes the user can receive in one reply:**

- **Text** — short prose, Markdown-rendered.
- **Value** — a single big number with a label and optional unit (e.g. `Total revenue 2026 YTD — €1,234,567.89`).
- **Table** — columns + rows, paginated client-side past 50 rows, with "Copy CSV".
- **Chart** — a Plotly figure (bar, line, pie, etc.) rendered via `Plotly.newPlot`.
- **Report** — a longer rendered document inline, with a "Download PDF" button.

Multiple blocks can appear in one reply (e.g. text + table + chart).

## 4. Architecture

```
Browser (ui/chat/index.html + chat.js)
    │  POST /chat (SSE response)
    ▼
FastAPI app  (logic/chat/app.py)
    │
    ├── ChatService               # global singleton: conversation history + agent loop
    │     │
    │     ├── Anthropic SDK       # Claude Sonnet 4.6, prompt caching on schema segment
    │     │     │
    │     │     └── tool: run_query(sql: str)
    │     │           │
    │     │           ▼
    │     ├── SqlExecutor         # parse → reject non-SELECT → cap rows → timeout → execute
    │     │     │
    │     │     └── SQLAlchemy session (read-only DB user) → SQL Server
    │     │
    │     └── AuditLog            # append-only logs/queries.jsonl
    │
    ├── PdfRenderer               # WeasyPrint, in-memory report store
    │
    └── static mount → ui/chat/
```

## 5. Backend components

### 5.1 `logic/chat/app.py` — FastAPI entry point

Endpoints:

- `POST /chat` — body `{ "message": "<user text>" }`, response is `text/event-stream` (SSE). Each event is one JSON object: `status`, `block`, `error`, or `done`. See §6 for the event protocol.
- `POST /chat/reset` — clears the global conversation. Returns `{ "ok": true }`.
- `GET /report/{report_id}/pdf` — returns `application/pdf`; 404 if the report id is unknown or expired (reports live in-memory only, evicted on reset or LRU past ~20).
- `GET /config` — returns `{"voice_lang": "<CHAT_VOICE_LANG>"}` for the frontend.
- `GET /` and `/static/*` — serves `ui/chat/`.

The app is started with `uvicorn logic.chat.app:app --reload` (matches the run command in [CLAUDE.md](../../../CLAUDE.md)).

### 5.2 `logic/chat/service.py` — ChatService

A single global instance per process. Holds:

- `messages: list[anthropic.MessageParam]` — the conversation history sent to Claude each turn.
- A bounded counter `queries_this_turn` reset at the start of each user turn; if it exceeds 10, the agent loop aborts with a friendly error block.

`async def stream_turn(user_message: str) -> AsyncIterator[SseEvent]` runs the agent loop:

1. Append `{role:"user", content: user_message}` to history.
2. `yield status("thinking")`.
3. Call `anthropic.messages.create(...)` with:
   - `model="claude-sonnet-4-6"`
   - System prompt = base instructions + schema reference (cached, see §5.3).
   - `tools=[run_query_spec]`.
   - `messages = self.messages`.
4. If the response contains tool-use blocks, for each one:
   - `yield status("querying", sql=...)`.
   - Run `SqlExecutor.run_query(sql)`.
   - Append a `tool_result` to history with the rows or the structured error.
   - Loop back to step 3.
5. When the response is the final assistant message, parse its text content as JSON matching the `Envelope` schema (§5.6). Append the assistant message to history. Emit each block as a `block` SSE event, then each citation as a `citation` SSE event, then `done`.
6. Any uncaught exception emits an `error` event and ends the stream; history is left unchanged for that turn (the failed user message is rolled back).

### 5.3 `logic/chat/schema_context.py`

Loads `docs/db_schema.md` once at startup. Builds two cached strings:

- `BASE_INSTRUCTIONS` — short prose explaining: the AI's role, the response envelope JSON schema, the rules (read-only, must cite SQL via the audit channel, when in doubt ask a clarifying question).
- `SCHEMA_REFERENCE` — the full file contents.

The Anthropic call wraps `SCHEMA_REFERENCE` in a `system` block with `cache_control: {"type": "ephemeral"}` so it is cached after turn 1. `BASE_INSTRUCTIONS` is a separate non-cached system block (cheap, evolves with the prompt).

### 5.4 `logic/chat/sql_executor.py`

`class SqlExecutor` exposes one method: `run_query(sql: str) -> QueryResult | QueryError`.

Validation pipeline (in order, each step short-circuits to a `QueryError`):

1. **Strip / parse.** Compute a "normalised" form by removing leading/trailing whitespace and stripping line/block comments. The normalised form is used **only** for validation in steps 2–4. The SQL actually executed (after wrapping in step 5) is the original string Claude provided.
2. **Single statement.** Reject if more than one statement is present (count semicolons that are not inside string literals or comments).
3. **Must start with SELECT or WITH** (case-insensitive, after step 1).
4. **Forbidden tokens** at word boundaries (case-insensitive): `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE`, `EXEC`, `EXECUTE`, `xp_`, `sp_`, `INTO` (catches `SELECT … INTO`).
5. **Wrap for row cap.** Final SQL sent to the DB is `SELECT TOP (1000) * FROM (\n<sql>\n) AS _capped`.
6. **Execute** through a SQLAlchemy session opened in autocommit-off, configured with `statement_timeout` / `LOCK_TIMEOUT 5000` and a Python-side wall-clock timeout of 30 s (raised as `QueryError(code="timeout")`).

Return shape:

```python
@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]   # JSON-serialisable scalars
    row_count: int
    truncated: bool         # True if row_count == 1000
    duration_ms: int

@dataclass
class QueryError:
    code: str               # "rejected" | "syntax" | "timeout" | "db_error"
    message: str            # human-readable, safe to show Claude
```

Both are serialised to JSON and returned to Claude as the tool result so it can react (retry with a corrected query, refine for truncation, etc.).

**Defense in depth — DB user.** The `DATABASE_URL` for this app points at a SQL Server login with `db_datareader` only, no `db_datawriter`, no `EXECUTE`. Verified manually before first run; documented in `.env.example`.

### 5.5 `logic/chat/audit.py`

`append(entry: dict) -> None` opens `logs/queries.jsonl` in append mode, writes one JSON line, flushes, closes. Wraps every `SqlExecutor.run_query` call regardless of outcome.

Entry shape:

```json
{
  "ts": "2026-05-28T14:23:11.123Z",
  "turn_id": "t_<uuid4>",
  "user_msg": "<the user's text for the current turn>",
  "sql": "<exact SQL sent to the DB, or the rejected SQL>",
  "rows": 847,
  "duration_ms": 423,
  "status": "ok",
  "error_code": null
}
```

A write failure on the audit log is logged via Python's `logging` but never raises into the request path — losing an audit row must not crash the chat.

`logs/` is added to `.gitignore`.

### 5.6 `logic/chat/envelope.py`

Pydantic v2 models:

```python
class TextBlock(BaseModel):    kind: Literal["text"];    markdown: str
class ValueBlock(BaseModel):   kind: Literal["value"];   label: str; value: float | int | str; unit: str | None = None
class TableBlock(BaseModel):   kind: Literal["table"];   columns: list[str]; rows: list[list[Any]]; caption: str | None = None
class ChartBlock(BaseModel):   kind: Literal["chart"];   title: str; plotly: dict   # {"data": [...], "layout": {...}}
class ReportBlock(BaseModel):  kind: Literal["report"];  id: str; title: str; html: str; pdf_url: str

Block = Annotated[Union[TextBlock, ValueBlock, TableBlock, ChartBlock, ReportBlock], Field(discriminator="kind")]

class Citation(BaseModel):     summary: str; sql_log_id: str | None = None

class Envelope(BaseModel):     blocks: list[Block]; citations: list[Citation] = []
```

The agent's final message must parse as `Envelope`. Parse failures abort the turn with an `error` SSE event (no fallback rendering).

### 5.7 `logic/chat/pdf.py`

`render_report(html: str, title: str) -> str` (returns a `report_id`). Stores `(html, title, generated_at)` in an LRU dict capped at 20 entries.

`get_pdf(report_id: str) -> bytes` renders the HTML to PDF via WeasyPrint at request time (not at registration — so we don't pay for PDFs the user never downloads). A baseline `report.css` (in `ui/chat/`) provides print-friendly styling.

**Fallback:** if WeasyPrint cannot be imported (e.g., GTK runtime missing on Windows), `/report/{id}/pdf` returns 501 with a JSON body explaining the user should use the inline view + browser print. The UI checks this on first PDF click and degrades gracefully.

### 5.8 `logic/chat/prompts.py`

Defines:

- `BASE_INSTRUCTIONS` — describes the agent's role, the read-only contract, the response envelope JSON schema (inline, as documentation Claude can read), and instructions for citations.
- `RUN_QUERY_TOOL` — the Anthropic tool spec:
  ```python
  {
    "name": "run_query",
    "description": "Run a SELECT query against the ERP database. Returns columns and rows, or a structured error. Limited to 1000 rows and 30s.",
    "input_schema": {
      "type": "object",
      "properties": {"sql": {"type": "string"}},
      "required": ["sql"]
    }
  }
  ```

## 6. SSE event protocol

`POST /chat` returns `text/event-stream`. Each event is `data: <json>\n\n` with one of:

| Event | Payload | Meaning |
|---|---|---|
| `status` | `{"phase":"thinking"}` or `{"phase":"querying","sql":"..."}` | Progress hint for the UI to show a spinner / "running query…" pill. |
| `block` | One block from the envelope (e.g. `{"kind":"table",...}`) | Append to the current assistant message in the UI. |
| `citation` | One `Citation` object | Optional — UI shows a small "show SQL" affordance. |
| `done` | `{}` | Stream finished cleanly. |
| `error` | `{"message":"...","code":"..."}` | Stream finished with an error; UI shows an inline error bubble. |

The frontend reads events sequentially and renders incrementally.

## 7. Frontend (`ui/chat/`)

**`index.html`** — three regions: header (title + "New chat"), message list, input bar.

**`chat.js`** — modules:

- `sse.js` — wraps `fetch` with `ReadableStream` to consume SSE (the `EventSource` API doesn't support POST bodies).
- `voice.js` — wraps `SpeechRecognition`. Exposes `start()`, `stop()`, `onresult(text)`. Hides itself if the API is missing.
- `renderers/` — one render function per block kind:
  - `text.js` → `marked.parse()` + sanitize via `DOMPurify`.
  - `value.js` → big-number card.
  - `table.js` → HTML `<table>` with simple pagination + CSV copy.
  - `chart.js` → `Plotly.newPlot(div, block.plotly.data, block.plotly.layout, {responsive:true})`.
  - `report.js` → injects `html` (sanitized) + a "Download PDF" anchor pointing at `pdf_url`.
- `app.js` — wires it all together; maintains the on-screen message list; calls `/chat/reset` on the new-chat button.

**`chat.css`** — minimal: ~150 lines of plain CSS, system fonts, light theme.

**Vendor scripts** — Plotly, marked, DOMPurify loaded from CDN with SRI hashes pinned. (If offline-first matters later, copy to `ui/chat/vendor/`.)

## 8. Configuration

Two existing environment variables are reused; one is added.

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Claude access. Required. |
| `DATABASE_URL` | SQLAlchemy URL pointing at a **read-only** SQL Server login. Required. |
| `CHAT_VOICE_LANG` (new) | BCP-47 tag passed to `SpeechRecognition.lang`. Default `pt-PT`. |

The frontend reads `CHAT_VOICE_LANG` via a tiny `GET /config` endpoint that returns `{"voice_lang": "pt-PT"}` (only this one field for now). `chat.js` fetches it on startup before initialising `voice.js`.

`.env.example` updated with the new variable and a note that the DB user must be read-only.

## 9. Testing

`tests/chat/`:

- **`test_sql_executor.py`** — exhaustive guardrail tests:
  - Accept: `SELECT 1`, `select 1`, `  -- comment\nSELECT 1`, `WITH cte AS (SELECT 1) SELECT * FROM cte`, real example queries from `docs/db_schema.md`.
  - Reject: empty, `DROP TABLE x`, `SELECT 1; DROP TABLE x`, `EXEC sp_help`, `SELECT * INTO x FROM y`, `WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d`, comment-hidden `/* … */ DROP …`, two statements separated by `;` inside the SQL.
  - Row cap: stub session returning 2000 rows → result is capped at 1000 and `truncated=True`.
  - Timeout: stub session that sleeps → raises `QueryError(code="timeout")` within 30 s.
- **`test_envelope.py`** — round-trip every block kind through JSON; reject unknown `kind`; reject extra fields if Pydantic is configured strict.
- **`test_audit.py`** — append + read back; corrupt-line tolerance on read; write failure does not raise.
- **`test_service.py`** — `ChatService` driven by a `FakeAnthropicClient` that scripts (a) immediate text answer, (b) one tool-use round-trip, (c) malformed JSON in the final message, (d) > 10 queries in one turn. Asserts the SSE event sequence each case produces.
- **`test_app.py`** — `httpx.AsyncClient` against the FastAPI app: `/chat/reset`, a happy-path `/chat` turn (with fakes wired via dependency overrides), `/report/{id}/pdf` 404 path and (if WeasyPrint importable) one render path.

Run: `pytest tests/chat/`.

**Manual smoke** (documented in the implementation plan, not automated): start the server against a real DevDB read-only login and ask:

1. "How many invoices are there in 2026?" → expect `value` block.
2. "Top 10 customers by revenue in 2026." → expect `table` block.
3. "Monthly revenue trend for 2026." → expect `chart` block.
4. "Sales summary report for Q1 2026." → expect `report` block with working PDF download.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Claude invents tables or columns not in the schema | Full schema is in the system prompt; the `run_query` error path returns the DB's message ("Invalid object name 'X'") so Claude can self-correct. |
| Long-running queries lock the server | 30 s wall-clock timeout + `LOCK_TIMEOUT 5000` + row cap. Per-turn query budget (10) prevents runaway loops. |
| SQL injection via the user message | The user message never becomes SQL directly — Claude writes SQL. The guardrails treat Claude's SQL as untrusted (read-only login is the last line of defense). |
| WeasyPrint install fails on Windows | The app starts even if WeasyPrint can't import; the PDF endpoint returns 501; the UI falls back to browser print. |
| 45k-token schema blows up cost | Prompt caching on the schema segment — after turn 1 in a conversation, schema tokens are billed at the 10% cache-read rate. New conversations re-warm the cache. |
| Browser speech recognition unsupported | Mic button hidden; text input works identically. |

## 11. Open questions (deferred to implementation)

- Exact WeasyPrint Windows install steps — confirm wheel + GTK during task setup, document in README.
- Whether to send a `keep-alive` ping on the SSE stream during long queries — decide once we measure typical query times.

## 12. References

- [CLAUDE.md](../../../CLAUDE.md) — project principles.
- [docs/db_schema.md](../../db_schema.md) — schema reference loaded into the system prompt.
- Anthropic prompt caching: `cache_control: {"type":"ephemeral"}` on the `system` block carrying the schema.
- Plotly.js, marked, DOMPurify — frontend vendor scripts.
- Web Speech API (`SpeechRecognition`) — browser-native voice input.
