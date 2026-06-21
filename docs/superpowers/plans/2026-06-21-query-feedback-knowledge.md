# Query Feedback → Durable Knowledge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a developer capture the business logic behind a wrong query, in-app, into a versioned knowledge document that the chat assistant loads into its context so corrections persist across sessions.

**Architecture:** A new `KnowledgeStore` owns `business_rules/query_knowledge.md` (read as a cached system block, allocate `KE-NNNN` ids, append entries). `ChatService` gains a `draft_entry` (Claude drafts a knowledge block) and `save_entry` (append + audit), and appends the knowledge block to its system prompt. Three developer-gated FastAPI endpoints (`/feedback/enabled`, `/feedback/draft`, `/feedback/save`) drive a "Teach / Fix" panel in the chat UI. The gate is a single `CHAT_FEEDBACK_TOKEN` env var.

**Tech Stack:** Python 3.12, FastAPI, Anthropic SDK, pytest, vanilla JS (existing `ui/chat`).

## Global Constraints

- Python 3.12 (`requires-python = ">=3.12,<3.14"`).
- No business logic in the UI or DB layer; rules live in versioned documents under `business_rules/` (CLAUDE.md). Keep the AI system prompt thin — reference the document, do not duplicate rules into the prompt.
- Audit trail is non-negotiable: every knowledge write produces a `queries.jsonl` line.
- Surgical changes: match existing style in `logic/chat`; every changed line traces to this feature.
- All new system-prompt text blocks that carry the knowledge doc use `cache_control: {"type": "ephemeral"}`, matching `SchemaContext`.
- Tests: pytest, `from __future__ import annotations` at top of each module, `tmp_path`/`monkeypatch` fixtures as in `tests/chat/`.

---

### Task 1: KnowledgeStore

**Files:**
- Create: `logic/chat/knowledge_store.py`
- Test: `tests/chat/test_knowledge_store.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `KnowledgeStore(path: Path | str)`
  - `KnowledgeStore.system_block() -> dict | None` — cached Anthropic text block, or `None` when the file is absent/blank.
  - `KnowledgeStore.next_id() -> str` — next `"KE-NNNN"` (zero-padded width 4).
  - `KnowledgeStore.append_entry(markdown: str, source_turn_id: str) -> str` — allocate id, normalize the `### ` heading to `### {ke_id} — {title}`, append a system-generated Provenance line, write, return the `ke_id`.

- [ ] **Step 1: Write the failing test**

```python
# tests/chat/test_knowledge_store.py
from __future__ import annotations
from pathlib import Path

from logic.chat.knowledge_store import KnowledgeStore


def test_system_block_none_when_absent(tmp_path: Path):
    store = KnowledgeStore(tmp_path / "query_knowledge.md")
    assert store.system_block() is None


def test_system_block_none_when_blank(tmp_path: Path):
    p = tmp_path / "query_knowledge.md"
    p.write_text("   \n\n", encoding="utf-8")
    assert KnowledgeStore(p).system_block() is None


def test_system_block_cached_text_when_present(tmp_path: Path):
    p = tmp_path / "query_knowledge.md"
    p.write_text("# Query Knowledge\nKE-0001 net sales rule", encoding="utf-8")
    block = KnowledgeStore(p).system_block()
    assert block["type"] == "text"
    assert block["cache_control"] == {"type": "ephemeral"}
    assert "net sales rule" in block["text"]


def test_next_id_starts_at_one(tmp_path: Path):
    assert KnowledgeStore(tmp_path / "k.md").next_id() == "KE-0001"


def test_append_allocates_sequential_ids_and_heading(tmp_path: Path):
    p = tmp_path / "k.md"
    store = KnowledgeStore(p)
    id1 = store.append_entry("### Net sales definition\n- **Business rule:** subtract credit notes", "t_abc")
    id2 = store.append_entry("### Active patients\n- **Business rule:** Estado=1", "t_def")
    assert (id1, id2) == ("KE-0001", "KE-0002")
    text = p.read_text(encoding="utf-8")
    assert "### KE-0001 — Net sales definition" in text
    assert "### KE-0002 — Active patients" in text


def test_append_adds_provenance_and_rewrites_existing_id(tmp_path: Path):
    p = tmp_path / "k.md"
    store = KnowledgeStore(p)
    # heading already carries a (stale) id — it must be rewritten, not duplicated
    ke = store.append_entry("### KE-9999 — Net sales\n- **Business rule:** x", "t_xyz")
    text = p.read_text(encoding="utf-8")
    assert ke == "KE-0001"
    assert "### KE-0001 — Net sales" in text
    assert "KE-9999" not in text
    assert "**Provenance:**" in text
    assert "t_xyz" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/chat/test_knowledge_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.chat.knowledge_store'`

- [ ] **Step 3: Write minimal implementation**

```python
# logic/chat/knowledge_store.py
from __future__ import annotations
import re
from datetime import date
from pathlib import Path

_HEADING_RE = re.compile(r"^###\s+(?:KE-\d+\s+—\s+)?(.*\S)\s*$", re.MULTILINE)
_ID_RE = re.compile(r"^###\s+KE-(\d+)\b", re.MULTILINE)

_FILE_HEADER = (
    "# Query Knowledge — Business rules for interpreting questions\n\n"
    "Authoritative business rules for translating user questions into SQL. "
    "Prefer them over inference. Note the KE id you applied in your citation.\n"
)


class KnowledgeStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def _read(self) -> str:
        if not self._path.exists():
            return ""
        return self._path.read_text(encoding="utf-8")

    def system_block(self) -> dict | None:
        text = self._read()
        if not text.strip():
            return None
        return {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }

    def next_id(self) -> str:
        nums = [int(m) for m in _ID_RE.findall(self._read())]
        return f"KE-{(max(nums) + 1) if nums else 1:04d}"

    def append_entry(self, markdown: str, source_turn_id: str) -> str:
        ke_id = self.next_id()
        body = markdown.strip()
        m = _HEADING_RE.search(body)
        title = m.group(1) if m else "Untitled"
        if m:
            body = body[:m.start()] + f"### {ke_id} — {title}" + body[m.end():]
        else:
            body = f"### {ke_id} — {title}\n" + body
        provenance = f"- **Provenance:** added {date.today().isoformat()} · source turn {source_turn_id}"
        entry = body.rstrip() + "\n" + provenance + "\n"

        existing = self._read()
        if not existing.strip():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            out = _FILE_HEADER + "\n" + entry
        else:
            out = existing.rstrip() + "\n\n" + entry
        self._path.write_text(out, encoding="utf-8")
        return ke_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/chat/test_knowledge_store.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add logic/chat/knowledge_store.py tests/chat/test_knowledge_store.py
git commit -m "feat(chat): KnowledgeStore for query_knowledge.md (read/append/id)"
```

---

### Task 2: Load knowledge into the system prompt

**Files:**
- Modify: `logic/chat/service.py` (`ChatService.__init__`, `_call_claude`)
- Modify: `logic/chat/prompts.py` (one pointer line in `BASE_INSTRUCTIONS`)
- Modify: `logic/chat/app.py` (`get_service` wiring, `_KNOWLEDGE_PATH`)
- Test: `tests/chat/test_service_knowledge.py`

**Interfaces:**
- Consumes: `KnowledgeStore` (Task 1); `SchemaContext.system_blocks()`.
- Produces: `ChatService(..., knowledge_store: KnowledgeStore)` — new required keyword arg; `_call_claude` sends `schema blocks + [knowledge block]` when the knowledge block is non-empty.

- [ ] **Step 1: Write the failing test**

```python
# tests/chat/test_service_knowledge.py
from __future__ import annotations
import asyncio
from pathlib import Path
from types import SimpleNamespace

from logic.chat.knowledge_store import KnowledgeStore
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService


def _service(tmp_path: Path, knowledge_text: str | None):
    schema = tmp_path / "schema.md"
    schema.write_text("SCHEMA_HERE", encoding="utf-8")
    kpath = tmp_path / "query_knowledge.md"
    if knowledge_text is not None:
        kpath.write_text(knowledge_text, encoding="utf-8")
    captured: dict = {}

    def _create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="{}")], usage=None)

    client = SimpleNamespace(messages=SimpleNamespace(create=_create))
    svc = ChatService(
        anthropic_client=client,
        sql_executor=SimpleNamespace(),
        audit=SimpleNamespace(),
        schema_context=SchemaContext(schema),
        report_store=SimpleNamespace(),
        history=SimpleNamespace(),
        knowledge_store=KnowledgeStore(kpath),
        model="claude-sonnet-4-6",
    )
    return svc, captured


def test_knowledge_block_included_when_present(tmp_path: Path):
    svc, captured = _service(tmp_path, "# Query Knowledge\nKE-0001 rule about net sales")
    asyncio.run(svc._call_claude([{"role": "user", "content": "hi"}]))
    system_text = " ".join(b["text"] for b in captured["system"])
    assert "net sales" in system_text


def test_knowledge_block_omitted_when_absent(tmp_path: Path):
    svc, captured = _service(tmp_path, None)
    asyncio.run(svc._call_claude([{"role": "user", "content": "hi"}]))
    # only base-instructions + schema blocks
    assert len(captured["system"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/chat/test_service_knowledge.py -v`
Expected: FAIL — `TypeError: ChatService.__init__() got an unexpected keyword argument 'knowledge_store'`

- [ ] **Step 3: Write minimal implementation**

In `logic/chat/service.py`, add the import near the other `logic.chat` imports:

```python
from logic.chat.knowledge_store import KnowledgeStore
```

Add the parameter to `ChatService.__init__` (keep all existing params; insert `knowledge_store` before `model`):

```python
        history: HistoryStore,
        knowledge_store: KnowledgeStore,
        model: str,
    ) -> None:
        self._anthropic = anthropic_client
        self._sql = sql_executor
        self._audit = audit
        self._schema = schema_context
        self._reports = report_store
        self._history = history
        self._knowledge = knowledge_store
        self._model = model
        self._bg_tasks: set[asyncio.Task] = set()
```

In `_call_claude`, build the system blocks with the knowledge block appended:

```python
    async def _call_claude(self, transcript: list[dict]) -> Any:
        system_blocks = self._schema.system_blocks()
        knowledge_block = self._knowledge.system_block()
        if knowledge_block is not None:
            system_blocks = system_blocks + [knowledge_block]
        kwargs = dict(
            model=self._model,
            max_tokens=4096,
            system=system_blocks,
            tools=[RUN_QUERY_TOOL],
            messages=_compress_past_turns_for_claude(transcript),
        )
```

In `logic/chat/prompts.py`, add one bullet to the `Rules:` list in `BASE_INSTRUCTIONS` (immediately after the "Use the schema reference..." rule):

```
- Business rules for interpreting questions may appear as a QUERY KNOWLEDGE document in your system context. When present, treat those rules as authoritative over your own inference, and note the KE id you applied in the relevant citation's summary.
```

In `logic/chat/app.py`, add the path constant near `_SCHEMA_PATH`:

```python
_KNOWLEDGE_PATH: Path = _REPO_ROOT / "business_rules" / "query_knowledge.md"
```

Add the import near the other `logic.chat` imports:

```python
from logic.chat.knowledge_store import KnowledgeStore
```

Wire it into `get_service()` (insert before `model=`):

```python
            history=_get_history(),
            knowledge_store=KnowledgeStore(_KNOWLEDGE_PATH),
            model="claude-sonnet-4-6",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chat/test_service_knowledge.py tests/chat/test_app.py tests/chat/test_schema_context.py -v`
Expected: PASS (existing app tests still green — `get_service` now passes the new arg)

- [ ] **Step 5: Commit**

```bash
git add logic/chat/service.py logic/chat/prompts.py logic/chat/app.py tests/chat/test_service_knowledge.py
git commit -m "feat(chat): load query_knowledge.md into the assistant system prompt"
```

---

### Task 3: ChatService.draft_entry

**Files:**
- Modify: `logic/chat/service.py` (add `draft_entry`)
- Modify: `logic/chat/prompts.py` (add `DRAFT_ENTRY_INSTRUCTIONS`)
- Test: `tests/chat/test_draft_entry.py`

**Interfaces:**
- Consumes: `self._anthropic`, `self._schema`, `self._model` (Task 2).
- Produces: `async ChatService.draft_entry(question: str, sql: str, explanation: str) -> str` — returns proposed KE markdown (a `### Title` heading + bullet fields, **no** id, **no** provenance).

- [ ] **Step 1: Write the failing test**

```python
# tests/chat/test_draft_entry.py
from __future__ import annotations
import asyncio
from pathlib import Path
from types import SimpleNamespace

from logic.chat.knowledge_store import KnowledgeStore
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService


def _service(tmp_path: Path, draft_text: str):
    schema = tmp_path / "schema.md"
    schema.write_text("SCHEMA_HERE", encoding="utf-8")
    captured: dict = {}

    def _create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=draft_text)], usage=None)

    client = SimpleNamespace(messages=SimpleNamespace(create=_create))
    svc = ChatService(
        anthropic_client=client,
        sql_executor=SimpleNamespace(),
        audit=SimpleNamespace(),
        schema_context=SchemaContext(schema),
        report_store=SimpleNamespace(),
        history=SimpleNamespace(),
        knowledge_store=KnowledgeStore(tmp_path / "k.md"),
        model="claude-sonnet-4-6",
    )
    return svc, captured


def test_draft_entry_returns_model_text(tmp_path: Path):
    draft = "### Net sales definition\n- **Business rule:** subtract credit notes"
    svc, captured = _service(tmp_path, draft)
    out = asyncio.run(svc.draft_entry("what were net sales?", "SELECT SUM(Total) ...", "must subtract credit notes"))
    assert out.strip() == draft
    # the developer's explanation is passed to the model
    user_msg = captured["messages"][0]["content"]
    assert "subtract credit notes" in user_msg
    # schema is available so the model can map to columns
    assert any("SCHEMA_HERE" in b["text"] for b in captured["system"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/chat/test_draft_entry.py -v`
Expected: FAIL — `AttributeError: 'ChatService' object has no attribute 'draft_entry'`

- [ ] **Step 3: Write minimal implementation**

In `logic/chat/prompts.py`, add:

```python
DRAFT_ENTRY_INSTRUCTIONS = """\
A developer is correcting how a question was answered. Write ONE knowledge entry
capturing the reusable business rule, so future questions are answered correctly.

Output Markdown ONLY, in exactly this shape (no id, no provenance, no code fences):

### <short title>
- **Intent:** <kinds of questions this applies to>
- **Business rule:** <the rule in plain terms — the developer's explanation>
- **Schema mapping:** <tables/columns/filters that encode the rule>
- **Example query:** `<a correct SELECT>`
- **Scope:** <database name(s)>

Question: {question}
SQL that ran (wrong): {sql}
Developer explanation: {explanation}
"""
```

In `logic/chat/service.py`, update the prompts import to include the new template:

```python
from logic.chat.prompts import DRAFT_ENTRY_INSTRUCTIONS, RUN_QUERY_TOOL
```

Add the method to `ChatService` (place it after `_call_claude`):

```python
    async def draft_entry(self, question: str, sql: str, explanation: str) -> str:
        prompt = DRAFT_ENTRY_INSTRUCTIONS.format(
            question=question, sql=sql, explanation=explanation
        )
        result = self._anthropic.messages.create(
            model=self._model,
            max_tokens=1024,
            system=self._schema.system_blocks(),
            messages=[{"role": "user", "content": prompt}],
        )
        if asyncio.iscoroutine(result):
            result = await result
        return "".join(
            getattr(c, "text", "") for c in result.content
            if getattr(c, "type", None) == "text"
        ).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/chat/test_draft_entry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logic/chat/service.py logic/chat/prompts.py tests/chat/test_draft_entry.py
git commit -m "feat(chat): ChatService.draft_entry drafts a knowledge entry via Claude"
```

---

### Task 4: Feedback endpoints, gate, save + audit

**Files:**
- Modify: `logic/chat/service.py` (add `save_entry`)
- Modify: `logic/chat/app.py` (gate helper + 3 endpoints)
- Modify: `.env.example` (`CHAT_FEEDBACK_TOKEN`)
- Test: `tests/chat/test_feedback.py`

**Interfaces:**
- Consumes: `ChatService.draft_entry` (Task 3); `KnowledgeStore.append_entry` (Task 1); `AuditLog.append`, `AuditLog.now_iso`.
- Produces:
  - `ChatService.save_entry(*, entry: str, question: str, explanation: str, source_turn_id: str, conversation_id: str) -> str` — append entry, write audit line, return `ke_id`.
  - `GET /feedback/enabled -> {"enabled": bool}`
  - `POST /feedback/draft` (gated) body `{question, sql, explanation}` → `{"entry": str}`
  - `POST /feedback/save` (gated) body `{entry, question, explanation, source_turn_id, conversation_id}` → `{"ke_id": str}`
  - Gate: feature off (no token) → 404 on draft/save; token present but header mismatch → 403.

- [ ] **Step 1: Write the failing test**

```python
# tests/chat/test_feedback.py
from __future__ import annotations
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from logic.chat import app as app_module


class _FakeSession:
    def execute(self, stmt) -> Any:
        class _R:
            def keys(self_inner): return []
            def fetchall(self_inner): return []
        return _R()


@contextmanager
def _factory() -> Iterator[_FakeSession]:
    yield _FakeSession()


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> Iterator[TestClient]:
    schema = tmp_path / "schema.md"
    schema.write_text("SCHEMA", encoding="utf-8")
    monkeypatch.setattr(app_module, "_SCHEMA_PATH", schema)
    monkeypatch.setattr(app_module, "_KNOWLEDGE_PATH", tmp_path / "query_knowledge.md")
    monkeypatch.setattr(app_module, "_LOG_PATH", tmp_path / "queries.jsonl")
    monkeypatch.setattr(app_module, "_HISTORY_PATH", tmp_path / "history.sqlite")
    monkeypatch.setattr(app_module, "_session_factory", _factory)
    monkeypatch.setattr(app_module, "_build_anthropic_client", lambda: SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
            content=[SimpleNamespace(type="text", text="### Net sales\n- **Business rule:** subtract credit notes")],
            usage=None,
        ))
    ))
    monkeypatch.setenv("CHAT_FEEDBACK_TOKEN", "s3cret")
    app_module.reset_service()
    with TestClient(app_module.app) as c:
        yield c


def test_enabled_true_when_token_set(client):
    assert client.get("/feedback/enabled").json() == {"enabled": True}


def test_draft_requires_token(client):
    r = client.post("/feedback/draft", json={"question": "q", "sql": "s", "explanation": "e"})
    assert r.status_code == 403


def test_draft_returns_entry_with_token(client):
    r = client.post("/feedback/draft",
                    headers={"X-Feedback-Token": "s3cret"},
                    json={"question": "net sales?", "sql": "SELECT 1", "explanation": "subtract credit notes"})
    assert r.status_code == 200
    assert "subtract credit notes" in r.json()["entry"]


def test_save_appends_and_audits(client, tmp_path: Path):
    r = client.post("/feedback/save",
                    headers={"X-Feedback-Token": "s3cret"},
                    json={"entry": "### Net sales\n- **Business rule:** subtract credit notes",
                          "question": "net sales?", "explanation": "subtract credit notes",
                          "source_turn_id": "t_1", "conversation_id": "c_1"})
    assert r.status_code == 200
    assert r.json()["ke_id"] == "KE-0001"
    # file written
    kfile = tmp_path / "query_knowledge.md"
    assert "### KE-0001 — Net sales" in kfile.read_text(encoding="utf-8")
    # audit line written
    lines = (tmp_path / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(l) for l in lines]
    assert any(e.get("kind") == "knowledge_entry" and e.get("ke_id") == "KE-0001" for e in entries)


def test_disabled_when_no_token(tmp_path: Path, monkeypatch):
    schema = tmp_path / "schema.md"; schema.write_text("S", encoding="utf-8")
    monkeypatch.setattr(app_module, "_SCHEMA_PATH", schema)
    monkeypatch.setattr(app_module, "_KNOWLEDGE_PATH", tmp_path / "k.md")
    monkeypatch.setattr(app_module, "_LOG_PATH", tmp_path / "q.jsonl")
    monkeypatch.setattr(app_module, "_HISTORY_PATH", tmp_path / "h.sqlite")
    monkeypatch.setattr(app_module, "_session_factory", _factory)
    monkeypatch.delenv("CHAT_FEEDBACK_TOKEN", raising=False)
    app_module.reset_service()
    with TestClient(app_module.app) as c:
        assert c.get("/feedback/enabled").json() == {"enabled": False}
        r = c.post("/feedback/draft", json={"question": "q", "sql": "s", "explanation": "e"})
        assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/chat/test_feedback.py -v`
Expected: FAIL — 404 for `/feedback/enabled` (routes not defined yet)

- [ ] **Step 3: Write minimal implementation**

In `logic/chat/service.py`, add to `ChatService`:

```python
    def save_entry(
        self, *, entry: str, question: str, explanation: str,
        source_turn_id: str, conversation_id: str,
    ) -> str:
        ke_id = self._knowledge.append_entry(entry, source_turn_id)
        self._audit.append({
            "ts": self._audit.now_iso(),
            "kind": "knowledge_entry",
            "ke_id": ke_id,
            "source_turn_id": source_turn_id,
            "conversation_id": conversation_id,
            "question": question,
            "explanation": explanation,
            "entry": entry,
        })
        return ke_id
```

Note: `AuditLog.now_iso` is a `@staticmethod`; calling it via `self._audit.now_iso()` works.

In `logic/chat/app.py`, add `import secrets` is already present. Add the gate helper and routes (place after the `/chat` route, before the static mount):

```python
def _feedback_token() -> str | None:
    return os.environ.get("CHAT_FEEDBACK_TOKEN") or None


def _require_feedback(request: Request) -> None:
    token = _feedback_token()
    if not token:
        raise HTTPException(status_code=404, detail="feedback disabled")
    provided = request.headers.get("X-Feedback-Token", "")
    if not secrets.compare_digest(provided, token):
        raise HTTPException(status_code=403, detail="invalid feedback token")


@app.get("/feedback/enabled")
def feedback_enabled() -> dict:
    return {"enabled": _feedback_token() is not None}


@app.post("/feedback/draft")
async def feedback_draft(request: Request) -> dict:
    _require_feedback(request)
    body = await request.json()
    entry = await get_service().draft_entry(
        body.get("question", ""), body.get("sql", ""), body.get("explanation", ""),
    )
    return {"entry": entry}


@app.post("/feedback/save")
async def feedback_save(request: Request) -> dict:
    _require_feedback(request)
    body = await request.json()
    ke_id = get_service().save_entry(
        entry=body.get("entry", ""),
        question=body.get("question", ""),
        explanation=body.get("explanation", ""),
        source_turn_id=body.get("source_turn_id", ""),
        conversation_id=body.get("conversation_id", ""),
    )
    return {"ke_id": ke_id}
```

In `.env.example`, append:

```
# Developer-only gate for the in-chat query-feedback feature (unset = feature off)
CHAT_FEEDBACK_TOKEN=
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chat/test_feedback.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Run the full chat suite for regressions**

Run: `pytest tests/chat/ -v`
Expected: PASS (all green)

- [ ] **Step 6: Commit**

```bash
git add logic/chat/service.py logic/chat/app.py .env.example tests/chat/test_feedback.py
git commit -m "feat(chat): developer-gated feedback endpoints (draft/save) + audit"
```

---

### Task 5: "Teach / Fix" panel in the chat UI

**Files:**
- Modify: `ui/chat/app.js` (unlock control + per-answer "Teach / Fix" affordance + panel)
- Modify: `ui/chat/chat.css` (panel styling, following existing classes)
- Test: manual (no JS test harness exists in this project)

**Interfaces:**
- Consumes: `GET /feedback/enabled`, `POST /feedback/draft`, `POST /feedback/save`.
- The SQL to pre-fill comes from the answer's `query` steps (the SSE `step` events with `type: "query"` carry `sql`). Reuse whatever structure `app.js` already stores per turn for the Details/steps view.

> Frontend is not TDD'd here. Keep changes minimal and follow the existing vanilla-JS patterns in `app.js` (no framework, no build step). Verify manually per Step 5.

- [ ] **Step 1: Gate the feature on load**

In `app.js`, on startup, fetch `/feedback/enabled`. Store the boolean. If false, render nothing feedback-related. If true, show a small "🔓 Dev" control in the header that prompts for the token (e.g. `window.prompt`) and stores it in `localStorage` under `feedback_token`. All feedback requests send header `X-Feedback-Token: <stored token>`.

- [ ] **Step 2: Add a "Teach / Fix" button per assistant answer**

When the feature is enabled and a token is stored, render a small "Teach / Fix" link/button on each completed assistant turn. Clicking it opens the panel for that turn, pre-filled with:
- the user's question (the turn's user message), and
- the SQL that ran — concatenate the `sql` of that turn's `query` steps (most recent first), editable.

- [ ] **Step 3: Wire Draft → edit → Save**

Panel has: a read-only/edit question, the SQL (editable textarea), a "Business logic explanation" textarea, a **Draft** button, a result textarea (the drafted entry, editable), and a **Save** button.
- **Draft** → `POST /feedback/draft` with `{question, sql, explanation}` and the token header → put `entry` into the result textarea.
- **Save** → `POST /feedback/save` with `{entry, question, explanation, source_turn_id, conversation_id}` and the token header → on `{ke_id}`, show a confirmation (e.g. "Saved KE-0001") and close the panel.

Use the turn's id for `source_turn_id` if available in the rendered turn data; otherwise send `""` (the audit line still records the rest).

- [ ] **Step 4: Style the panel**

Add classes in `chat.css` consistent with existing panels (reuse existing color variables / spacing). No new dependencies.

- [ ] **Step 5: Manual verification**

```bash
# Terminal: set a token and run the server
# (PowerShell)  $env:CHAT_FEEDBACK_TOKEN = "devtoken"
uvicorn logic.chat.app:app --reload
```
Then in the browser at http://localhost:8000/ :
1. Confirm the "🔓 Dev" control appears; enter `devtoken`.
2. Ask a question that produces a SQL query.
3. Click "Teach / Fix" → confirm question + SQL are pre-filled.
4. Type an explanation → **Draft** → a structured KE entry appears.
5. **Save** → confirmation shows `KE-0001`.
6. Confirm `business_rules/query_knowledge.md` now contains `### KE-0001 — …` with a Provenance line, and `logs/queries.jsonl` has a `kind:"knowledge_entry"` line.
7. Ask the same question again in a new conversation → the assistant applies the rule (cites the KE id).

Also confirm the feature is invisible when the server runs without `CHAT_FEEDBACK_TOKEN`.

- [ ] **Step 6: Commit**

```bash
git add ui/chat/app.js ui/chat/chat.css
git commit -m "feat(chat-ui): developer Teach/Fix panel for query feedback"
```

---

## Self-Review

**Spec coverage:**
- Knowledge doc + format → Task 1 (store) + Task 4 (first save creates the file with header).
- In-app flow (question + SQL prefill, draft, save, optional re-run) → Task 5. *Optional "re-run with this knowledge"* is intentionally omitted from v1 build steps (manual re-ask covers it; the spec marked it optional).
- Gate (`CHAT_FEEDBACK_TOKEN`, enabled/disabled, 404/403) → Task 4.
- Loading & application (3rd cached block, thin prompt pointer) → Task 2.
- Audit (`kind:"knowledge_entry"`) → Task 4.
- Out-of-scope items (git commit on save, edit/delete via UI, retrieval) → not built, consistent with spec.

**Placeholder scan:** No TBD/TODO. Code shown for every code step. Task 5 (frontend) uses descriptive steps with concrete endpoints/fields and a manual verification script — acceptable since the repo has no JS test harness and the spec keeps UI minimal.

**Type consistency:** `KnowledgeStore.append_entry(markdown, source_turn_id) -> str`, `system_block() -> dict | None`, `next_id() -> str` used identically in Tasks 1/2/4. `ChatService.draft_entry(question, sql, explanation)` and `save_entry(*, entry, question, explanation, source_turn_id, conversation_id)` match between Task 3/4 definitions and the app endpoints that call them. `knowledge_store` keyword arg added in Task 2 is supplied by `get_service` (Task 2) and present for Tasks 3/4 tests.

**Note for implementer:** Tasks 2–4 modify `ChatService.__init__`; any other construction site of `ChatService` must pass `knowledge_store`. Current only sites: `app.get_service` (updated in Task 2) and the test helpers above.
