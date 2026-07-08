# Query Feedback → Durable Knowledge — Design

**Date:** 2026-06-21
**Status:** Approved (design); pending implementation plan
**Module:** `logic/chat` (read/query path)

## Problem

The chat assistant (`logic/chat`) translates natural-language questions into SQL
via the `run_query` tool. Its only context is `BASE_INSTRUCTIONS` plus the full
`docs/db_schema.md`, loaded into the system prompt. There is **no business-rule
layer on the read/query path** and **no mechanism to retain corrections**: every
turn starts from the same static context.

When a generated query runs successfully but is *semantically wrong for the
user's intent* (e.g. "net sales" computed without subtracting credit notes),
there is nowhere to capture the correct business logic, and nothing carries that
correction into future interactions. The existing audit log (`queries.jsonl`)
records whether SQL *executed*, not whether it was *correct*.

## Goal

When a query is wrong, let the **developer explain the business logic** behind
the correct interpretation, capture that explanation as a durable, versioned
**knowledge entry**, and load it into the assistant's context so the same mistake
is not repeated in future interactions — for every session, not just the current
one.

This extends the project's AI-native principle (business rules live in versioned
documents under `business_rules/`, not in code) to the query path, which today
has no such layer.

## Decisions (from brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Primary loop | Durable knowledge doc | Corrections must persist across sessions. |
| Capture path | Agent-drafted, developer-approved | Low friction; every entry intentional; developer stays gatekeeper. |
| Where the loop runs | Inside the chat app | Capture in the moment, without leaving the app. |
| Trust model | Developer-only (gated) | Writing a rule changes everyone's answers; one trusted role. |
| Storage/application | Flat curated Markdown, always loaded (Approach A) | Simplest; matches `db_schema.md`; cache-friendly; clean migration path. |
| Commit to git | Manual, out of band (not in v1) | Saved rule works immediately on disk; versioning is a separate dev step. |

## Architecture

```
ui/chat/  ── "Teach / Fix" panel (dev-gated)
   │  question + SQL-that-ran (from query steps) + developer explanation
   ▼
logic/chat/app.py
   ├── GET  /feedback/enabled         # is the feature on (token configured)?
   ├── POST /feedback/draft   (gated) # → Claude drafts a KE block
   └── POST /feedback/save    (gated) # → append KE block, audit
   │
   ├── KnowledgeStore (new: logic/chat/knowledge_store.py)
   │     read_block() → cached system block | allocate KE id | append_entry()
   ├── ChatService.draft_entry(...)   # Claude call to draft a KE block
   └── AuditLog                       # kind:"knowledge_entry" line on save

system prompt = BASE_INSTRUCTIONS + db_schema.md + query_knowledge.md  (all cached)
```

### Component boundaries

- **`KnowledgeStore`** (`logic/chat/knowledge_store.py`) — single purpose: own the
  `business_rules/query_knowledge.md` file. Methods:
  - `system_block() -> dict | None` — return the doc as a cached Anthropic text
    block, or `None` if the file is absent/empty. Re-reads the file each call so
    a freshly saved rule takes effect on the next turn.
  - `next_id() -> str` — allocate the next `KE-NNNN` id by scanning existing entries.
  - `append_entry(markdown: str) -> None` — append a rendered KE block.
  Mirrors the shape of `report_store.py` / `audit.py`. Independently testable
  with a temp file; no Anthropic or DB dependency.

- **`ChatService.draft_entry(question, sql, explanation) -> str`** — calls Claude
  (the configured chat model) with the schema context + inputs, returns a
  proposed KE markdown block. Drafting lives here because it needs the Anthropic
  client the service already owns. No file I/O.

- **`app.py`** — wires the three endpoints, the gate, and composes system blocks
  as schema + knowledge.

- **`SchemaContext`** — unchanged except that the assembled system blocks now
  include the knowledge block. Composition happens where `system_blocks()` is
  consumed (`ChatService._call_claude`), which appends `KnowledgeStore.system_block()`
  if present.

## Knowledge document format

New file `business_rules/query_knowledge.md`. Header explains the contract; then
append-only structured entries with stable ids.

```markdown
# Query Knowledge — Business rules for interpreting questions

These are authoritative business rules for translating user questions into SQL.
Prefer them over inference. Cite the KE id you applied in your citations.

### KE-0001 — Net sales definition
- **Intent:** "net sales" / "net revenue" / "faturação líquida"
- **Business rule:** Net sales = invoices (TipoDoc=1) minus credit notes
  (TipoDoc=3); exclude cancelled documents (Estado=0). Returns are subtracted,
  not ignored.
- **Schema mapping:** Doc001.TipoDoc, Doc001.Estado, Doc001.Total (+ LinDoc001 for lines)
- **Example query:** `SELECT SUM(CASE WHEN TipoDoc=3 THEN -Total ELSE Total END) ...`
- **Scope:** DevDB, ForumSI
- **Provenance:** added 2026-06-21 · source turn t_abc123
```

Fields per entry: **Intent**, **Business rule**, **Schema mapping**,
**Example query**, **Scope**, **Provenance**. The **Business rule** field is the
durable developer explanation — the reusable "why".

## In-app flow

1. Each assistant answer in `ui/chat/` shows a **"Teach / Fix"** control, visible
   only when the feature is unlocked.
2. The control opens a panel pre-filled with the user question and **the SQL that
   actually ran** (read from the answer's `query` steps — already streamed, no new
   plumbing). The developer types the business-logic explanation and, optionally,
   what the correct answer/shape should be.
3. **Draft** → `POST /feedback/draft` → `ChatService.draft_entry(...)` → returns a
   proposed KE block. The panel shows it; the developer edits freely.
4. **Save** → `POST /feedback/save` → `KnowledgeStore.append_entry(...)` + audit line.
5. **Optional "re-run with this knowledge"** — re-issues the original question in a
   scratch turn so the developer can verify the new query is correct. (Implement if
   cheap; otherwise the developer asks the question again manually.)

## The gate

- Env var `CHAT_FEEDBACK_TOKEN`. If **unset**, the feedback feature is disabled:
  `GET /feedback/enabled` returns `{"enabled": false}` and `draft`/`save` return
  404. Feature is simply off in any deploy without a token.
- If set, the developer enters the token once in the UI; it is stored client-side
  (cookie/localStorage) and sent as a request header (e.g. `X-Feedback-Token`).
- Backend validates with `secrets.compare_digest`. No user accounts or real auth
  system are introduced — consistent with the current anonymous-cookie setup.

## Loading & application

- `ChatService._call_claude` assembles `system = SchemaContext.system_blocks() +
  [KnowledgeStore.system_block()]` (the latter appended only when non-empty). All
  blocks keep `cache_control: ephemeral`; Anthropic's prompt cache re-keys
  automatically when the knowledge content changes, so a newly saved rule
  invalidates the stale cache and takes effect on the next turn.
- `BASE_INSTRUCTIONS` gains one thin line pointing at the QUERY KNOWLEDGE document
  as authoritative, instructing Claude to cite the applied KE id. Rules are **not**
  duplicated into the prompt — the document is the source of truth (per CLAUDE.md
  "keep the AI's system prompt thin; load the document dynamically").

## Audit

On save, `queries.jsonl` gets a line with `kind:"knowledge_entry"`: `ke_id`, `ts`,
`source_turn_id`, `conversation_id`, the question, the developer explanation, and
the saved entry text. Each KE entry also records inline provenance (added date +
source turn). Satisfies the non-negotiable audit-trail constraint.

## Out of scope (v1)

- **Git commit on save.** The app writes to the server's working copy; committing
  to version control is a manual developer step. Acceptable for the single-instance
  dev setup.
- **Editing/deleting entries via UI.** Edit `query_knowledge.md` directly.
- **Retrieval/ranking.** The whole doc is always loaded (Approach A). Revisit token
  cost at a few dozen entries; per-entry structure keeps migration to retrieval easy.
- **End-user (non-developer) feedback.** Deferred; trust model is developer-only.

## Testing

| Area | Test |
|---|---|
| Gate | `/feedback/draft` and `/feedback/save` reject missing/invalid token; `/feedback/enabled` reflects whether `CHAT_FEEDBACK_TOKEN` is set. |
| `KnowledgeStore` | `next_id` allocates sequential `KE-NNNN`; `append_entry` round-trips; `system_block()` returns `None` for absent/empty file, a cached block otherwise. |
| System blocks | Knowledge block is included when the file exists and omitted when absent. |
| Drafting | `draft_entry` returns a well-formed KE block from a fake Anthropic client given (question, SQL, explanation). |
| Audit | A `kind:"knowledge_entry"` line is written on save with the expected fields. |
| Application | A turn run with a populated knowledge doc sends the rule text in the system blocks to the (fake) Anthropic client. |

## Success criteria

1. A developer can, from the chat UI (unlocked), turn a wrong answer + an
   explanation into a saved KE entry without leaving the app.
2. After saving, asking the same question applies the new rule (verifiable via the
   re-run step or by re-asking).
3. The entry persists and is loaded into context in a brand-new session.
4. Every saved entry produces an audit line; the feature is disabled when no token
   is configured.

## Files touched

- New: `logic/chat/knowledge_store.py`, `business_rules/query_knowledge.md`
  (created on first save), tests under `tests/chat/`.
- Modified: `logic/chat/app.py` (endpoints + gate + system-block composition),
  `logic/chat/service.py` (`draft_entry`, append knowledge block in `_call_claude`),
  `logic/chat/prompts.py` (one pointer line), `ui/chat/` (Teach/Fix panel),
  `.env.example` (`CHAT_FEEDBACK_TOKEN`).
