# Conversational DB Chat UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a single-page conversational UI that lets one user query the existing SQL Server ERP database by voice or text. Claude generates read-only SQL via a tool-use loop; the assistant returns a typed envelope (text / value / table / chart / report) that the frontend renders, with downloadable PDF reports.

**Architecture:** FastAPI serves a static HTML page and a streaming `/chat` SSE endpoint. A `ChatService` singleton owns the conversation history and the agent loop with Claude (Sonnet 4.6). A `SqlExecutor` validates every tool call (SELECT-only) before executing through a read-only SQLAlchemy session. Reports render to PDF on demand via WeasyPrint (graceful 501 fallback). All queries are appended to `logs/queries.jsonl`.

**Tech Stack:** Python 3.12+, FastAPI, Uvicorn, SQLAlchemy 2.0 + pyodbc, Anthropic SDK, Pydantic v2, WeasyPrint, pytest + pytest-asyncio + httpx. Frontend is plain HTML/CSS/JS with Plotly, marked, DOMPurify from CDN.

**Spec:** [`docs/superpowers/specs/2026-05-28-conversational-db-chat-ui-design.md`](../specs/2026-05-28-conversational-db-chat-ui-design.md)

---

## File Structure

```
ERP_Agent/
├── pyproject.toml                                          [modify]
├── .env.example                                            [modify]
├── .gitignore                                              [modify]
├── docs/db_schema.md                                       [no change — loaded at runtime]
├── logic/
│   └── chat/
│       ├── __init__.py                                     [create]
│       ├── app.py                                          [create — FastAPI app + endpoints]
│       ├── service.py                                      [create — ChatService agent loop]
│       ├── envelope.py                                     [create — Pydantic block/envelope models]
│       ├── schema_context.py                               [create — load docs/db_schema.md]
│       ├── sql_executor.py                                 [create — validate + cap + execute]
│       ├── audit.py                                        [create — append-only JSONL]
│       ├── pdf.py                                          [create — WeasyPrint + LRU store]
│       └── prompts.py                                      [create — BASE_INSTRUCTIONS + RUN_QUERY_TOOL]
├── ui/
│   └── chat/
│       ├── index.html                                      [create]
│       ├── chat.css                                        [create]
│       ├── app.js                                          [create — wiring + message list]
│       ├── sse.js                                          [create — fetch-based SSE client]
│       ├── voice.js                                        [create — Web Speech API wrapper]
│       └── renderers/
│           ├── text.js                                     [create]
│           ├── value.js                                    [create]
│           ├── table.js                                    [create]
│           ├── chart.js                                    [create — Plotly.newPlot]
│           └── report.js                                   [create — html + PDF link]
├── logs/                                                   [gitignored, created at runtime]
└── tests/
    └── chat/
        ├── __init__.py                                     [create]
        ├── conftest.py                                     [create — shared fixtures]
        ├── test_envelope.py                                [create]
        ├── test_audit.py                                   [create]
        ├── test_sql_validator.py                           [create]
        ├── test_sql_executor.py                            [create]
        ├── test_schema_context.py                          [create]
        ├── test_prompts.py                                 [create]
        ├── test_pdf.py                                     [create]
        ├── test_service.py                                 [create]
        └── test_app.py                                     [create]
```

---

## Conventions

- All new modules use `from __future__ import annotations`.
- Pydantic v2 models use `model_config = ConfigDict(extra="forbid")`.
- Pure-function/validator code is unit-tested directly. IO-bound code is tested through a fake (no live DB, no live Anthropic).
- Each task ends with a green test run **and** a commit. Commit messages follow the existing repo style (`feat:`, `chore:`, `test:`, `docs:`).
- `tests/chat/__init__.py` exists from Task 2 onward; the test runner is `pytest tests/chat/`.

---

## Tasks

### Task 1: Add dependencies, env vars, and gitignore entry

**Files:**
- Modify: `pyproject.toml`
- Modify: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Add WeasyPrint to dependencies**

In `pyproject.toml`, add `"weasyprint>=62.0"` to the `dependencies` list (alongside the existing `anthropic`, `pydantic`, etc.).

- [ ] **Step 2: Add the new env var and note about read-only DB user**

Append to `.env.example`:

```
# Chat UI — BCP-47 tag for browser speech recognition (default pt-PT)
CHAT_VOICE_LANG=pt-PT

# IMPORTANT: the DATABASE_URL above must use a SQL Server login
# with db_datareader only — no db_datawriter, no EXECUTE grants.
```

- [ ] **Step 3: Gitignore the runtime log directory**

Append to `.gitignore`:

```
logs/
```

- [ ] **Step 4: Install dependencies**

Run: `pip install -e ".[dev]"`
Expected: WeasyPrint installs cleanly. On Windows, if you see a GTK-related error, it's expected — Task 9 includes the graceful-fallback path. Note the error, continue.

- [ ] **Step 5: Commit**

```
git add pyproject.toml .env.example .gitignore
git commit -m "chore: add weasyprint + chat env vars + gitignore logs/"
```

---

### Task 2: Create package skeleton

**Files:**
- Create: `logic/chat/__init__.py` (empty)
- Create: `tests/chat/__init__.py` (empty)
- Create: `tests/chat/conftest.py`

- [ ] **Step 1: Create empty package files**

Both `logic/chat/__init__.py` and `tests/chat/__init__.py` are empty files.

- [ ] **Step 2: Create the shared test fixture**

`tests/chat/conftest.py`:

```python
from __future__ import annotations
from pathlib import Path
import pytest


@pytest.fixture
def tmp_log_path(tmp_path: Path) -> Path:
    return tmp_path / "queries.jsonl"
```

- [ ] **Step 3: Verify pytest discovers the package**

Run: `pytest tests/chat/ --collect-only -q`
Expected: `no tests ran` (no tests yet) — but no collection errors.

- [ ] **Step 4: Commit**

```
git add logic/chat tests/chat
git commit -m "chore: scaffold logic/chat and tests/chat packages"
```

---

### Task 3: Envelope models

**Files:**
- Create: `logic/chat/envelope.py`
- Create: `tests/chat/test_envelope.py`

- [ ] **Step 1: Write the failing tests**

`tests/chat/test_envelope.py`:

```python
from __future__ import annotations
import pytest
from pydantic import ValidationError

from logic.chat.envelope import (
    ChartBlock,
    Citation,
    ClaudeEnvelope,
    RawReportBlock,
    ReportBlock,
    TableBlock,
    TextBlock,
    ValueBlock,
)


def test_text_block_roundtrip():
    b = TextBlock(markdown="**hi**")
    assert b.model_dump() == {"kind": "text", "markdown": "**hi**"}


def test_value_block_optional_unit():
    b = ValueBlock(label="Revenue", value=123.45, unit="EUR")
    assert b.unit == "EUR"
    b2 = ValueBlock(label="Count", value=10)
    assert b2.unit is None


def test_table_block():
    b = TableBlock(columns=["a", "b"], rows=[[1, 2], [3, 4]])
    assert b.columns == ["a", "b"]
    assert b.rows == [[1, 2], [3, 4]]


def test_chart_block():
    b = ChartBlock(title="t", plotly={"data": [], "layout": {}})
    assert b.title == "t"


def test_raw_report_block_has_no_id_or_pdf_url():
    b = RawReportBlock(title="T", html="<p>x</p>")
    dumped = b.model_dump()
    assert "id" not in dumped
    assert "pdf_url" not in dumped


def test_report_block_requires_id_and_pdf_url():
    with pytest.raises(ValidationError):
        ReportBlock(title="T", html="<p>x</p>")  # missing id + pdf_url


def test_envelope_parses_mixed_blocks_from_json():
    payload = {
        "blocks": [
            {"kind": "text", "markdown": "hello"},
            {"kind": "value", "label": "n", "value": 1},
            {"kind": "table", "columns": ["x"], "rows": [[1]]},
            {"kind": "chart", "title": "t", "plotly": {"data": [], "layout": {}}},
            {"kind": "report", "title": "R", "html": "<p/>"},
        ],
        "citations": [{"summary": "top 10", "sql_log_id": "q_42"}],
    }
    env = ClaudeEnvelope.model_validate(payload)
    kinds = [b.kind for b in env.blocks]
    assert kinds == ["text", "value", "table", "chart", "report"]
    assert env.citations[0].sql_log_id == "q_42"


def test_envelope_rejects_unknown_kind():
    with pytest.raises(ValidationError):
        ClaudeEnvelope.model_validate({"blocks": [{"kind": "video", "url": "x"}], "citations": []})


def test_envelope_rejects_extra_fields_on_block():
    with pytest.raises(ValidationError):
        ClaudeEnvelope.model_validate(
            {"blocks": [{"kind": "text", "markdown": "hi", "extra": 1}], "citations": []}
        )


def test_citation_optional_sql_log_id():
    c = Citation(summary="x")
    assert c.sql_log_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chat/test_envelope.py -v`
Expected: collection error or `ImportError` — `logic.chat.envelope` does not exist yet.

- [ ] **Step 3: Implement envelope models**

`logic/chat/envelope.py`:

```python
from __future__ import annotations
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class TextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["text"] = "text"
    markdown: str


class ValueBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["value"] = "value"
    label: str
    value: float | int | str
    unit: str | None = None


class TableBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["table"] = "table"
    columns: list[str]
    rows: list[list[Any]]
    caption: str | None = None


class ChartBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["chart"] = "chart"
    title: str
    plotly: dict[str, Any]


class RawReportBlock(BaseModel):
    """Report shape produced by Claude. The server enriches it with id+pdf_url before emitting."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["report"] = "report"
    title: str
    html: str


class ReportBlock(BaseModel):
    """Report shape sent to the browser — id and pdf_url filled in by the server."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal["report"] = "report"
    id: str
    title: str
    html: str
    pdf_url: str


ClaudeBlock = Annotated[
    Union[TextBlock, ValueBlock, TableBlock, ChartBlock, RawReportBlock],
    Field(discriminator="kind"),
]

ClientBlock = Annotated[
    Union[TextBlock, ValueBlock, TableBlock, ChartBlock, ReportBlock],
    Field(discriminator="kind"),
]


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str
    sql_log_id: str | None = None


class ClaudeEnvelope(BaseModel):
    """The JSON object Claude returns as its final message."""
    model_config = ConfigDict(extra="forbid")
    blocks: list[ClaudeBlock]
    citations: list[Citation] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chat/test_envelope.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```
git add logic/chat/envelope.py tests/chat/test_envelope.py
git commit -m "feat: chat envelope models (Claude-side and client-side block types)"
```

---

### Task 4: Audit log

**Files:**
- Create: `logic/chat/audit.py`
- Create: `tests/chat/test_audit.py`

- [ ] **Step 1: Write the failing tests**

`tests/chat/test_audit.py`:

```python
from __future__ import annotations
import json
from pathlib import Path

from logic.chat.audit import AuditLog


def test_append_writes_one_jsonl_line(tmp_log_path: Path):
    log = AuditLog(tmp_log_path)
    log.append({"ts": "2026-05-28T10:00:00Z", "sql": "SELECT 1", "rows": 1, "status": "ok"})
    contents = tmp_log_path.read_text(encoding="utf-8")
    assert contents.count("\n") == 1
    parsed = json.loads(contents.strip())
    assert parsed["sql"] == "SELECT 1"


def test_append_creates_parent_directory(tmp_path: Path):
    nested = tmp_path / "deep" / "queries.jsonl"
    log = AuditLog(nested)
    log.append({"x": 1})
    assert nested.exists()


def test_append_multiple_entries(tmp_log_path: Path):
    log = AuditLog(tmp_log_path)
    for i in range(3):
        log.append({"i": i})
    lines = tmp_log_path.read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(line)["i"] for line in lines] == [0, 1, 2]


def test_append_does_not_raise_on_write_failure(tmp_path: Path, monkeypatch):
    log = AuditLog(tmp_path / "queries.jsonl")

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom)
    log.append({"x": 1})  # must not raise


def test_now_iso_format():
    s = AuditLog.now_iso()
    # 2026-05-28T14:23:11.123Z shape
    assert s.endswith("Z")
    assert "T" in s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chat/test_audit.py -v`
Expected: ImportError — module not present.

- [ ] **Step 3: Implement AuditLog**

`logic/chat/audit.py`:

```python
from __future__ import annotations
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


class AuditLog:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: dict[str, Any]) -> None:
        try:
            line = json.dumps(entry, separators=(",", ":"), default=str)
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            _log.exception("audit log write failed")

    @staticmethod
    def now_iso() -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chat/test_audit.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```
git add logic/chat/audit.py tests/chat/test_audit.py
git commit -m "feat: chat audit log (append-only JSONL, failure-tolerant)"
```

---

### Task 5: SQL validator (pure-function pipeline)

**Files:**
- Create: `logic/chat/sql_executor.py` (validator portion only — execution comes in Task 6)
- Create: `tests/chat/test_sql_validator.py`

- [ ] **Step 1: Write the failing tests**

`tests/chat/test_sql_validator.py`:

```python
from __future__ import annotations
import pytest

from logic.chat.sql_executor import QueryError, validate_sql


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "  SELECT 1  ",
    "select 1",
    "-- a comment\nSELECT 1",
    "/* block */ SELECT 1",
    "WITH cte AS (SELECT 1 AS x) SELECT * FROM cte",
    "SELECT a FROM t WHERE x = 'has ; inside'",
    "SELECT 1;",
])
def test_accepts_valid_select(sql):
    assert validate_sql(sql) is None


@pytest.mark.parametrize("sql,reason", [
    ("", "empty"),
    ("   ", "empty"),
    ("-- only comment", "empty"),
    ("DROP TABLE x", "forbidden"),
    ("DELETE FROM t", "forbidden"),
    ("UPDATE t SET x=1", "forbidden"),
    ("INSERT INTO t VALUES (1)", "forbidden"),
    ("SELECT 1; DROP TABLE x", "statement"),
    ("EXEC sp_help", "forbidden"),
    ("exec sp_help", "forbidden"),
    ("SELECT * INTO x FROM y", "forbidden"),
    ("WITH d AS (DELETE FROM t) SELECT * FROM d", "forbidden"),
    ("/* hide */ DROP TABLE x", "forbidden"),
    ("SELECT 1; SELECT 2", "statement"),
])
def test_rejects_invalid(sql, reason):
    result = validate_sql(sql)
    assert isinstance(result, QueryError), f"expected rejection for {sql!r}, got None"
    assert result.code == "rejected"


def test_trailing_semicolon_allowed():
    assert validate_sql("SELECT 1;") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chat/test_sql_validator.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement the validator and types**

`logic/chat/sql_executor.py`:

```python
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int


@dataclass
class QueryError:
    code: str  # "rejected" | "timeout" | "db_error"
    message: str


ROW_CAP = 1000
QUERY_TIMEOUT_S = 30

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")

_FORBIDDEN = re.compile(
    r"(?i)\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXEC|EXECUTE|INTO)\b"
    r"|\b(xp_|sp_)\w*",
)


def _normalise(sql: str) -> str:
    s = _BLOCK_COMMENT.sub(" ", sql)
    s = _LINE_COMMENT.sub(" ", s)
    return s.strip()


def _strip_string_literals(s: str) -> str:
    # Removes single/double-quoted strings so semicolons inside them don't count.
    return re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "", s)


def validate_sql(sql: str) -> QueryError | None:
    normalised = _normalise(sql)
    if not normalised:
        return QueryError(code="rejected", message="empty SQL")
    body = _strip_string_literals(normalised).rstrip(";")
    if ";" in body:
        return QueryError(code="rejected", message="only one statement allowed")
    if not re.match(r"^\s*(SELECT|WITH)\b", normalised, re.IGNORECASE):
        return QueryError(code="rejected", message="only SELECT or WITH allowed")
    m = _FORBIDDEN.search(normalised)
    if m:
        return QueryError(code="rejected", message=f"forbidden keyword: {m.group(0)}")
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chat/test_sql_validator.py -v`
Expected: every parametrised case passes.

- [ ] **Step 5: Commit**

```
git add logic/chat/sql_executor.py tests/chat/test_sql_validator.py
git commit -m "feat: SQL validator rejects writes and multi-statements"
```

---

### Task 6: SqlExecutor.run_query with row cap, timeout, fake session

**Files:**
- Modify: `logic/chat/sql_executor.py`
- Create: `tests/chat/test_sql_executor.py`

- [ ] **Step 1: Write the failing tests**

`tests/chat/test_sql_executor.py`:

```python
from __future__ import annotations
from contextlib import contextmanager
from typing import Any, Iterator

import pytest

from logic.chat.sql_executor import QueryError, QueryResult, ROW_CAP, SqlExecutor


class FakeResult:
    def __init__(self, columns: list[str], rows: list[list[Any]]) -> None:
        self._columns = columns
        self._rows = rows

    def keys(self) -> list[str]:
        return self._columns

    def fetchall(self) -> list[list[Any]]:
        return self._rows


class FakeSession:
    def __init__(self, *, rows: list[list[Any]], columns: list[str] | None = None,
                 raise_exc: Exception | None = None) -> None:
        self._rows = rows
        self._columns = columns or ["a", "b"]
        self._raise = raise_exc
        self.executed: list[str] = []

    def execute(self, stmt) -> FakeResult:
        sql = str(stmt) if not isinstance(stmt, str) else stmt
        self.executed.append(sql)
        if self._raise is not None:
            raise self._raise
        if "SET LOCK_TIMEOUT" in sql:
            return FakeResult([], [])
        return FakeResult(self._columns, self._rows)


def make_factory(session: FakeSession):
    @contextmanager
    def factory() -> Iterator[FakeSession]:
        yield session
    return factory


def test_run_query_happy_path():
    session = FakeSession(rows=[[1, 2], [3, 4]], columns=["x", "y"])
    ex = SqlExecutor(make_factory(session))
    result = ex.run_query("SELECT x, y FROM t")
    assert isinstance(result, QueryResult)
    assert result.columns == ["x", "y"]
    assert result.rows == [[1, 2], [3, 4]]
    assert result.row_count == 2
    assert result.truncated is False
    # the wrapped form was sent
    assert any("SELECT TOP (" in s for s in session.executed)


def test_run_query_truncates_at_row_cap():
    too_many = [[i] for i in range(ROW_CAP)]
    session = FakeSession(rows=too_many, columns=["i"])
    ex = SqlExecutor(make_factory(session))
    result = ex.run_query("SELECT i FROM t")
    assert isinstance(result, QueryResult)
    assert result.row_count == ROW_CAP
    assert result.truncated is True


def test_run_query_returns_error_on_rejection():
    session = FakeSession(rows=[])
    ex = SqlExecutor(make_factory(session))
    err = ex.run_query("DROP TABLE x")
    assert isinstance(err, QueryError)
    assert err.code == "rejected"
    assert session.executed == []  # never reached the DB


def test_run_query_wraps_db_error():
    session = FakeSession(rows=[], raise_exc=RuntimeError("connection lost"))
    ex = SqlExecutor(make_factory(session))
    err = ex.run_query("SELECT 1")
    assert isinstance(err, QueryError)
    assert err.code == "db_error"
    assert "connection lost" in err.message


def test_run_query_timeout(monkeypatch):
    import time as _time

    class SlowSession:
        executed: list[str] = []

        def execute(self, stmt):
            if "SET LOCK_TIMEOUT" in str(stmt):
                return FakeResult([], [])
            _time.sleep(2)
            return FakeResult(["x"], [[1]])

    @contextmanager
    def factory():
        yield SlowSession()

    # shorten timeout so the test finishes quickly
    monkeypatch.setattr("logic.chat.sql_executor.QUERY_TIMEOUT_S", 0.2)
    ex = SqlExecutor(factory)
    err = ex.run_query("SELECT 1")
    assert isinstance(err, QueryError)
    assert err.code == "timeout"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chat/test_sql_executor.py -v`
Expected: `SqlExecutor` not defined.

- [ ] **Step 3: Extend `sql_executor.py` with the executor**

Append to `logic/chat/sql_executor.py`:

```python
import concurrent.futures
import time
from contextlib import AbstractContextManager
from typing import Callable

from sqlalchemy import text


def _wrap(sql: str) -> str:
    body = sql.rstrip().rstrip(";")
    return f"SELECT TOP ({ROW_CAP}) * FROM (\n{body}\n) AS _capped"


class SqlExecutor:
    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Any]],
    ) -> None:
        self._session_factory = session_factory

    def run_query(self, sql: str) -> QueryResult | QueryError:
        err = validate_sql(sql)
        if err is not None:
            return err
        wrapped = _wrap(sql)
        start = time.monotonic()
        try:
            columns, rows = self._execute_with_timeout(wrapped, QUERY_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            return QueryError(code="timeout", message=f"query exceeded {QUERY_TIMEOUT_S}s")
        except Exception as e:
            return QueryError(code="db_error", message=str(e)[:500])
        duration_ms = int((time.monotonic() - start) * 1000)
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=len(rows) >= ROW_CAP,
            duration_ms=duration_ms,
        )

    def _execute_with_timeout(self, wrapped: str, timeout: float) -> tuple[list[str], list[list[Any]]]:
        def _work() -> tuple[list[str], list[list[Any]]]:
            with self._session_factory() as session:
                session.execute(text("SET LOCK_TIMEOUT 5000"))
                result = session.execute(text(wrapped))
                columns = list(result.keys())
                rows = [list(r) for r in result.fetchall()]
                return columns, rows

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_work)
            return fut.result(timeout=timeout)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chat/test_sql_executor.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```
git add logic/chat/sql_executor.py tests/chat/test_sql_executor.py
git commit -m "feat: SqlExecutor with row cap, wall-clock timeout, db_error wrapping"
```

---

### Task 7: Schema context loader

**Files:**
- Create: `logic/chat/schema_context.py`
- Create: `tests/chat/test_schema_context.py`

- [ ] **Step 1: Write the failing tests**

`tests/chat/test_schema_context.py`:

```python
from __future__ import annotations
from pathlib import Path

from logic.chat.schema_context import SchemaContext


def test_loads_schema_file(tmp_path: Path):
    p = tmp_path / "schema.md"
    p.write_text("# Schema\nTable foo.\n", encoding="utf-8")
    ctx = SchemaContext(schema_path=p)
    assert "Table foo" in ctx.schema_reference


def test_system_blocks_contain_schema_and_base_instructions(tmp_path: Path):
    p = tmp_path / "schema.md"
    p.write_text("SCHEMA_HERE", encoding="utf-8")
    ctx = SchemaContext(schema_path=p)
    blocks = ctx.system_blocks()
    assert isinstance(blocks, list) and len(blocks) == 2
    # base instructions block (no cache_control)
    assert blocks[0]["type"] == "text"
    assert "cache_control" not in blocks[0]
    assert "ERP" in blocks[0]["text"]
    # schema block (cached)
    assert blocks[1]["type"] == "text"
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}
    assert "SCHEMA_HERE" in blocks[1]["text"]


def test_missing_schema_file_raises(tmp_path: Path):
    import pytest
    with pytest.raises(FileNotFoundError):
        SchemaContext(schema_path=tmp_path / "nope.md")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chat/test_schema_context.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement SchemaContext**

`logic/chat/schema_context.py`:

```python
from __future__ import annotations
from pathlib import Path

from logic.chat.prompts import BASE_INSTRUCTIONS


class SchemaContext:
    def __init__(self, schema_path: Path | str) -> None:
        p = Path(schema_path)
        if not p.exists():
            raise FileNotFoundError(f"schema file not found: {p}")
        self.schema_reference = p.read_text(encoding="utf-8")

    def system_blocks(self) -> list[dict]:
        return [
            {"type": "text", "text": BASE_INSTRUCTIONS},
            {
                "type": "text",
                "text": self.schema_reference,
                "cache_control": {"type": "ephemeral"},
            },
        ]
```

> Note: this module imports `BASE_INSTRUCTIONS` from `logic.chat.prompts` — Task 8 creates that module. Implement Task 8 next; the tests in this task will fail with `ImportError` until then.

- [ ] **Step 4: Skip ahead momentarily — verify test failure mode**

Run: `pytest tests/chat/test_schema_context.py -v`
Expected: ImportError on `logic.chat.prompts`. This is expected — proceed to Task 8 before re-running.

- [ ] **Step 5: Do not commit yet**

This task's commit happens at the end of Task 8 alongside the prompts module.

---

### Task 8: Prompts module

**Files:**
- Create: `logic/chat/prompts.py`
- Create: `tests/chat/test_prompts.py`

- [ ] **Step 1: Write the failing tests**

`tests/chat/test_prompts.py`:

```python
from __future__ import annotations

from logic.chat.prompts import BASE_INSTRUCTIONS, RUN_QUERY_TOOL


def test_base_instructions_mention_envelope_and_readonly():
    assert "blocks" in BASE_INSTRUCTIONS
    assert "read-only" in BASE_INSTRUCTIONS.lower()
    assert "run_query" in BASE_INSTRUCTIONS


def test_run_query_tool_spec_shape():
    assert RUN_QUERY_TOOL["name"] == "run_query"
    assert "sql" in RUN_QUERY_TOOL["input_schema"]["properties"]
    assert RUN_QUERY_TOOL["input_schema"]["required"] == ["sql"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chat/test_prompts.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement prompts**

`logic/chat/prompts.py`:

```python
from __future__ import annotations

BASE_INSTRUCTIONS = """\
You are the assistant for an ERP system. You answer the user's questions by querying \
a SQL Server database (read-only) and returning structured results.

You MUST return your final reply as a single JSON object matching this schema:

{
  "blocks": [
    {"kind":"text",   "markdown":"<markdown text>"},
    {"kind":"value",  "label":"<label>", "value":<number or string>, "unit":"<optional>"},
    {"kind":"table",  "columns":[...], "rows":[[...], ...], "caption":"<optional>"},
    {"kind":"chart",  "title":"<title>", "plotly":{"data":[...],"layout":{...}}},
    {"kind":"report", "title":"<title>", "html":"<inline html>"}
  ],
  "citations": [
    {"summary":"<short description of the query>", "sql_log_id":null}
  ]
}

Rules:
- Read-only. You can only run SELECT or WITH statements via the run_query tool.
- Max 10 queries per turn. Max 1000 rows per query. Plan queries that fit.
- Use the schema reference in the system prompt as your source of truth for tables and columns.
- If the user's request is ambiguous, return a single text block asking a clarifying question.
- For numeric answers, use a value block. For lists/grids, use a table block. For trends/distributions, use a chart block. For multi-section narratives, use a report block.
- You can return multiple blocks in one reply (e.g. a short text summary plus a table plus a chart).
- Cite each significant query in the citations array.
- Reply with the JSON object only. No prose outside the JSON.
"""

RUN_QUERY_TOOL: dict = {
    "name": "run_query",
    "description": (
        "Run a single SELECT (or WITH) statement against the ERP database. "
        "Returns columns and rows, or a structured error. Capped at 1000 rows and 30s."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string"}},
        "required": ["sql"],
    },
}
```

- [ ] **Step 4: Run both prompts and schema-context tests**

Run: `pytest tests/chat/test_prompts.py tests/chat/test_schema_context.py -v`
Expected: all tests pass.

- [ ] **Step 5: Commit (covers Tasks 7 and 8)**

```
git add logic/chat/schema_context.py logic/chat/prompts.py tests/chat/test_schema_context.py tests/chat/test_prompts.py
git commit -m "feat: prompts + schema context (cached schema reference for Claude)"
```

---

### Task 9: PdfRenderer (LRU store + WeasyPrint with fallback)

**Files:**
- Create: `logic/chat/pdf.py`
- Create: `tests/chat/test_pdf.py`

- [ ] **Step 1: Write the failing tests**

`tests/chat/test_pdf.py`:

```python
from __future__ import annotations
import pytest

from logic.chat.pdf import PdfRenderer, ReportNotFound, WeasyPrintUnavailable


def test_register_returns_unique_ids():
    r = PdfRenderer()
    id1 = r.register("<p>1</p>", "T1")
    id2 = r.register("<p>2</p>", "T2")
    assert id1 != id2
    assert id1.startswith("r_")


def test_get_pdf_unknown_id_raises():
    r = PdfRenderer()
    with pytest.raises(ReportNotFound):
        r.get_pdf("r_does_not_exist")


def test_lru_eviction():
    r = PdfRenderer(max_entries=3)
    ids = [r.register(f"<p>{i}</p>", f"T{i}") for i in range(4)]
    with pytest.raises(ReportNotFound):
        r.get_pdf(ids[0])
    # newest 3 still resolvable
    assert r._has(ids[1]) and r._has(ids[2]) and r._has(ids[3])


def test_clear_drops_everything():
    r = PdfRenderer()
    rid = r.register("<p>x</p>", "T")
    r.clear()
    with pytest.raises(ReportNotFound):
        r.get_pdf(rid)


def test_get_pdf_renders_or_raises_unavailable(monkeypatch):
    r = PdfRenderer()
    rid = r.register("<p>Hello</p>", "Title")

    # Simulate weasyprint missing
    monkeypatch.setattr("logic.chat.pdf._weasyprint_available", lambda: False)
    with pytest.raises(WeasyPrintUnavailable):
        r.get_pdf(rid)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chat/test_pdf.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement PdfRenderer**

`logic/chat/pdf.py`:

```python
from __future__ import annotations
import secrets
from collections import OrderedDict
from typing import Any


class ReportNotFound(Exception):
    pass


class WeasyPrintUnavailable(Exception):
    pass


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
        return True
    except Exception:
        return False


class PdfRenderer:
    def __init__(self, max_entries: int = 20) -> None:
        self._max = max_entries
        self._store: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def register(self, html: str, title: str) -> str:
        rid = "r_" + secrets.token_hex(6)
        self._store[rid] = {"html": html, "title": title}
        self._store.move_to_end(rid)
        while len(self._store) > self._max:
            self._store.popitem(last=False)
        return rid

    def _has(self, report_id: str) -> bool:
        return report_id in self._store

    def get_pdf(self, report_id: str) -> bytes:
        if report_id not in self._store:
            raise ReportNotFound(report_id)
        if not _weasyprint_available():
            raise WeasyPrintUnavailable(
                "WeasyPrint is not installed or cannot be imported. "
                "Use the browser's Print > Save as PDF as a fallback."
            )
        import weasyprint
        entry = self._store[report_id]
        wrapped = (
            f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{entry['title']}</title>"
            f"<link rel='stylesheet' href='report.css'></head>"
            f"<body>{entry['html']}</body></html>"
        )
        return weasyprint.HTML(string=wrapped).write_pdf()

    def clear(self) -> None:
        self._store.clear()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chat/test_pdf.py -v`
Expected: all tests pass. On Windows where WeasyPrint may not import, the `_weasyprint_available` test still passes because it patches the function directly.

- [ ] **Step 5: Commit**

```
git add logic/chat/pdf.py tests/chat/test_pdf.py
git commit -m "feat: PdfRenderer with LRU store and WeasyPrint unavailability fallback"
```

---

### Task 10: ChatService — agent loop, query budget, envelope parsing

**Files:**
- Create: `logic/chat/service.py`
- Create: `tests/chat/test_service.py`

- [ ] **Step 1: Write the failing tests**

`tests/chat/test_service.py`:

```python
from __future__ import annotations
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from logic.chat.audit import AuditLog
from logic.chat.pdf import PdfRenderer
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService
from logic.chat.sql_executor import SqlExecutor


# --- fakes ---

class _ContentText:
    type = "text"
    def __init__(self, text: str) -> None:
        self.text = text


class _ContentToolUse:
    type = "tool_use"
    def __init__(self, tool_id: str, name: str, sql: str) -> None:
        self.id = tool_id
        self.name = name
        self.input = {"sql": sql}


class _Response:
    def __init__(self, content: list, stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason


class FakeAnthropicClient:
    def __init__(self, scripted: list[_Response]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw) -> _Response:
        self.calls.append(kw)
        if not self._scripted:
            raise AssertionError("FakeAnthropicClient ran out of scripted responses")
        return self._scripted.pop(0)


class _FakeSession:
    def execute(self, stmt) -> Any:
        s = str(stmt)
        class _R:
            def keys(self_inner): return ["n"]
            def fetchall(self_inner): return [[42]]
        if "SET LOCK_TIMEOUT" in s:
            class _Empty:
                def keys(self_inner): return []
                def fetchall(self_inner): return []
            return _Empty()
        return _R()


@contextmanager
def _factory() -> Iterator[_FakeSession]:
    yield _FakeSession()


@pytest.fixture
def schema_ctx(tmp_path: Path) -> SchemaContext:
    p = tmp_path / "schema.md"
    p.write_text("Tables: foo.", encoding="utf-8")
    return SchemaContext(schema_path=p)


@pytest.fixture
def audit(tmp_path: Path) -> AuditLog:
    return AuditLog(tmp_path / "queries.jsonl")


@pytest.fixture
def pdf_renderer() -> PdfRenderer:
    return PdfRenderer()


@pytest.fixture
def sql_executor() -> SqlExecutor:
    return SqlExecutor(_factory)


# --- tests ---

@pytest.mark.asyncio
async def test_immediate_text_reply_no_tool_use(schema_ctx, audit, pdf_renderer, sql_executor):
    envelope_json = json.dumps({"blocks": [{"kind": "text", "markdown": "hi"}], "citations": []})
    client = FakeAnthropicClient([_Response([_ContentText(envelope_json)], stop_reason="end_turn")])
    svc = ChatService(
        anthropic_client=client,
        sql_executor=sql_executor,
        audit=audit,
        schema_context=schema_ctx,
        pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    events = [e async for e in svc.stream_turn("hello")]
    types = [e["type"] for e in events]
    assert types[0] == "status"
    assert "block" in types
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_tool_use_round_trip(schema_ctx, audit, pdf_renderer, sql_executor):
    final = json.dumps({"blocks": [{"kind": "value", "label": "n", "value": 42}], "citations": []})
    client = FakeAnthropicClient([
        _Response([_ContentToolUse("t1", "run_query", "SELECT 42 AS n")], stop_reason="tool_use"),
        _Response([_ContentText(final)], stop_reason="end_turn"),
    ])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor,
        audit=audit, schema_context=schema_ctx, pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    events = [e async for e in svc.stream_turn("count")]
    # we should see a 'querying' status, then a value block
    statuses = [e for e in events if e["type"] == "status"]
    blocks = [e for e in events if e["type"] == "block"]
    assert any(s["payload"].get("phase") == "querying" for s in statuses)
    assert len(blocks) == 1 and blocks[0]["payload"]["kind"] == "value"
    # claude was called twice
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_query_budget_exceeded(schema_ctx, audit, pdf_renderer, sql_executor):
    # script 11 tool_use responses → loop should abort after the 10th
    tool_use = lambda i: _Response(
        [_ContentToolUse(f"t{i}", "run_query", f"SELECT {i}")],
        stop_reason="tool_use",
    )
    client = FakeAnthropicClient([tool_use(i) for i in range(11)])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor,
        audit=audit, schema_context=schema_ctx, pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    events = [e async for e in svc.stream_turn("loop")]
    errors = [e for e in events if e["type"] == "error"]
    assert errors and "budget" in errors[0]["payload"]["message"].lower()


@pytest.mark.asyncio
async def test_malformed_envelope_emits_error(schema_ctx, audit, pdf_renderer, sql_executor):
    client = FakeAnthropicClient([_Response([_ContentText("not json at all")], stop_reason="end_turn")])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor,
        audit=audit, schema_context=schema_ctx, pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    events = [e async for e in svc.stream_turn("x")]
    assert any(e["type"] == "error" for e in events)


@pytest.mark.asyncio
async def test_report_block_gets_id_and_pdf_url(schema_ctx, audit, pdf_renderer, sql_executor):
    env = json.dumps({
        "blocks": [{"kind": "report", "title": "T", "html": "<p>x</p>"}],
        "citations": [],
    })
    client = FakeAnthropicClient([_Response([_ContentText(env)], stop_reason="end_turn")])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor,
        audit=audit, schema_context=schema_ctx, pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    events = [e async for e in svc.stream_turn("report me")]
    report_blocks = [e for e in events if e["type"] == "block" and e["payload"]["kind"] == "report"]
    assert len(report_blocks) == 1
    p = report_blocks[0]["payload"]
    assert p["id"].startswith("r_")
    assert p["pdf_url"] == f"/report/{p['id']}/pdf"


def test_reset_clears_history(schema_ctx, audit, pdf_renderer, sql_executor):
    client = FakeAnthropicClient([])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor,
        audit=audit, schema_context=schema_ctx, pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    svc.messages.append({"role": "user", "content": "old"})
    svc.reset()
    assert svc.messages == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chat/test_service.py -v`
Expected: ImportError on `logic.chat.service`.

- [ ] **Step 3: Implement ChatService**

`logic/chat/service.py`:

```python
from __future__ import annotations
import json
import uuid
from dataclasses import asdict
from typing import Any, AsyncIterator

from pydantic import ValidationError

from logic.chat.audit import AuditLog
from logic.chat.envelope import ClaudeEnvelope, RawReportBlock, ReportBlock
from logic.chat.pdf import PdfRenderer
from logic.chat.prompts import RUN_QUERY_TOOL
from logic.chat.schema_context import SchemaContext
from logic.chat.sql_executor import QueryError, QueryResult, SqlExecutor


MAX_QUERIES_PER_TURN = 10


class ChatService:
    def __init__(
        self,
        *,
        anthropic_client: Any,
        sql_executor: SqlExecutor,
        audit: AuditLog,
        schema_context: SchemaContext,
        pdf_renderer: PdfRenderer,
        model: str,
    ) -> None:
        self._anthropic = anthropic_client
        self._sql = sql_executor
        self._audit = audit
        self._schema = schema_context
        self._pdf = pdf_renderer
        self._model = model
        self.messages: list[dict] = []

    def reset(self) -> None:
        self.messages = []
        self._pdf.clear()

    async def stream_turn(self, user_message: str) -> AsyncIterator[dict]:
        turn_id = "t_" + uuid.uuid4().hex[:12]
        history_before = list(self.messages)
        self.messages.append({"role": "user", "content": user_message})
        queries_used = 0

        try:
            yield {"type": "status", "payload": {"phase": "thinking"}}

            while True:
                response = self._anthropic.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    system=self._schema.system_blocks(),
                    tools=[RUN_QUERY_TOOL],
                    messages=self.messages,
                )

                tool_uses = [c for c in response.content if getattr(c, "type", None) == "tool_use"]

                if not tool_uses:
                    # final assistant message — parse envelope
                    text_parts = [c.text for c in response.content if getattr(c, "type", None) == "text"]
                    raw = "".join(text_parts).strip()
                    self.messages.append({"role": "assistant", "content": raw})
                    async for ev in self._emit_envelope(raw):
                        yield ev
                    yield {"type": "done", "payload": {}}
                    return

                # one or more tool calls — execute each, append to history, recurse
                assistant_blocks: list[dict] = []
                for tu in response.content:
                    if getattr(tu, "type", None) == "text":
                        assistant_blocks.append({"type": "text", "text": tu.text})
                    elif getattr(tu, "type", None) == "tool_use":
                        assistant_blocks.append({
                            "type": "tool_use",
                            "id": tu.id,
                            "name": tu.name,
                            "input": tu.input,
                        })
                self.messages.append({"role": "assistant", "content": assistant_blocks})

                tool_results: list[dict] = []
                for tu in tool_uses:
                    sql = tu.input.get("sql", "")
                    queries_used += 1
                    if queries_used > MAX_QUERIES_PER_TURN:
                        self.messages = history_before  # roll back this turn
                        yield {"type": "error", "payload": {
                            "code": "budget_exceeded",
                            "message": f"Query budget exceeded ({MAX_QUERIES_PER_TURN} per turn).",
                        }}
                        return

                    yield {"type": "status", "payload": {"phase": "querying", "sql": sql}}
                    result = self._sql.run_query(sql)
                    self._audit.append({
                        "ts": AuditLog.now_iso(),
                        "turn_id": turn_id,
                        "user_msg": user_message,
                        "sql": sql,
                        "rows": getattr(result, "row_count", None),
                        "duration_ms": getattr(result, "duration_ms", None),
                        "status": "ok" if isinstance(result, QueryResult) else "error",
                        "error_code": result.code if isinstance(result, QueryError) else None,
                    })
                    if isinstance(result, QueryResult):
                        tool_payload = {
                            "columns": result.columns,
                            "rows": result.rows,
                            "row_count": result.row_count,
                            "truncated": result.truncated,
                        }
                    else:
                        tool_payload = {"error": asdict(result)}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(tool_payload, default=str),
                    })

                self.messages.append({"role": "user", "content": tool_results})
                # loop back for the next Claude call
        except Exception as e:
            self.messages = history_before
            yield {"type": "error", "payload": {"code": "internal", "message": str(e)[:500]}}
            return

    async def _emit_envelope(self, raw: str) -> AsyncIterator[dict]:
        try:
            data = json.loads(raw)
            env = ClaudeEnvelope.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            yield {"type": "error", "payload": {
                "code": "envelope_parse",
                "message": f"could not parse assistant reply: {e}",
            }}
            return

        for block in env.blocks:
            if isinstance(block, RawReportBlock):
                rid = self._pdf.register(block.html, block.title)
                emitted = ReportBlock(
                    id=rid, title=block.title, html=block.html,
                    pdf_url=f"/report/{rid}/pdf",
                )
                yield {"type": "block", "payload": emitted.model_dump()}
            else:
                yield {"type": "block", "payload": block.model_dump()}

        for c in env.citations:
            yield {"type": "citation", "payload": c.model_dump()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/chat/test_service.py -v`
Expected: all 6 tests pass.

- [ ] **Step 5: Commit**

```
git add logic/chat/service.py tests/chat/test_service.py
git commit -m "feat: ChatService agent loop with tool-use, query budget, envelope emission"
```

---

### Task 11: FastAPI app — basic endpoints (`/config`, `/chat/reset`, `/report/{id}/pdf`)

**Files:**
- Create: `logic/chat/app.py`
- Create: `tests/chat/test_app.py`

- [ ] **Step 1: Write the failing tests**

`tests/chat/test_app.py`:

```python
from __future__ import annotations
import os
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
    # point app at a tmp schema file + tmp log path + a fake anthropic client
    schema = tmp_path / "schema.md"
    schema.write_text("SCHEMA", encoding="utf-8")
    monkeypatch.setenv("CHAT_VOICE_LANG", "en-US")
    monkeypatch.setattr(app_module, "_SCHEMA_PATH", schema)
    monkeypatch.setattr(app_module, "_LOG_PATH", tmp_path / "queries.jsonl")
    monkeypatch.setattr(app_module, "_session_factory", _factory)
    monkeypatch.setattr(app_module, "_build_anthropic_client", lambda: SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"blocks":[{"kind":"text","markdown":"hi"}],"citations":[]}')],
            stop_reason="end_turn",
        ))
    ))
    # rebuild service with the patched bits
    app_module.reset_service()
    with TestClient(app_module.app) as c:
        yield c


def test_config_returns_voice_lang(client):
    r = client.get("/config")
    assert r.status_code == 200
    assert r.json() == {"voice_lang": "en-US"}


def test_chat_reset(client):
    r = client.post("/chat/reset")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_report_pdf_404_for_unknown(client):
    r = client.get("/report/r_nope/pdf")
    assert r.status_code == 404


def test_static_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<!doctype html" in r.text.lower() or "<html" in r.text.lower()
```

> Note: `test_static_index_served` requires `ui/chat/index.html` to exist (Task 13). Until then, this test fails — that's acceptable; this commit ships the endpoints, Task 13 makes the static-serve test pass.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/chat/test_app.py -v`
Expected: ImportError on `logic.chat.app`.

- [ ] **Step 3: Implement the FastAPI app (without `/chat` SSE yet — that's Task 12)**

`logic/chat/app.py`:

```python
from __future__ import annotations
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from logic.chat.audit import AuditLog
from logic.chat.pdf import PdfRenderer, ReportNotFound, WeasyPrintUnavailable
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService
from logic.chat.sql_executor import SqlExecutor


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH: Path = _REPO_ROOT / "docs" / "db_schema.md"
_LOG_PATH: Path = _REPO_ROOT / "logs" / "queries.jsonl"
_UI_DIR: Path = _REPO_ROOT / "ui" / "chat"


@contextmanager
def _session_factory() -> Iterator[Session]:
    # Imported lazily so tests can monkeypatch this whole function.
    from db.connection import get_session
    with get_session() as s:
        yield s


def _build_anthropic_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


_service: ChatService | None = None


def get_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService(
            anthropic_client=_build_anthropic_client(),
            sql_executor=SqlExecutor(_session_factory),
            audit=AuditLog(_LOG_PATH),
            schema_context=SchemaContext(_SCHEMA_PATH),
            pdf_renderer=PdfRenderer(),
            model="claude-sonnet-4-6",
        )
    return _service


def reset_service() -> None:
    global _service
    _service = None


app = FastAPI(title="ERP Chat")


@app.get("/config")
def get_config() -> dict:
    return {"voice_lang": os.environ.get("CHAT_VOICE_LANG", "pt-PT")}


@app.post("/chat/reset")
def post_chat_reset() -> dict:
    svc = get_service()
    svc.reset()
    return {"ok": True}


@app.get("/report/{report_id}/pdf")
def get_report_pdf(report_id: str) -> Response:
    svc = get_service()
    try:
        pdf = svc._pdf.get_pdf(report_id)
    except ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found")
    except WeasyPrintUnavailable as e:
        return Response(
            content=str(e),
            status_code=501,
            media_type="text/plain",
        )
    return Response(content=pdf, media_type="application/pdf")


if _UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
```

- [ ] **Step 4: Run the three endpoint tests (skip the static-index one until Task 13)**

Run: `pytest tests/chat/test_app.py -v -k "not static_index"`
Expected: three tests pass (`test_config_returns_voice_lang`, `test_chat_reset`, `test_report_pdf_404_for_unknown`).

- [ ] **Step 5: Commit**

```
git add logic/chat/app.py tests/chat/test_app.py
git commit -m "feat: FastAPI app shell + /config, /chat/reset, /report/{id}/pdf"
```

---

### Task 12: FastAPI app — `/chat` SSE endpoint

**Files:**
- Modify: `logic/chat/app.py`
- Modify: `tests/chat/test_app.py`

- [ ] **Step 1: Add the SSE test**

Append to `tests/chat/test_app.py`:

```python
def test_chat_sse_streams_envelope(client):
    with client.stream("POST", "/chat", json={"message": "hi"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = b"".join(r.iter_bytes()).decode("utf-8")
    # We expect at least one status, one block, and one done event.
    assert "event: status" in body
    assert "event: block" in body
    assert "event: done" in body
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/chat/test_app.py::test_chat_sse_streams_envelope -v`
Expected: 404 (no `/chat` route).

- [ ] **Step 3: Add `/chat` SSE endpoint**

Append to `logic/chat/app.py` (above the `if _UI_DIR.exists():` line):

```python
import json as _json
from fastapi import Request
from fastapi.responses import StreamingResponse


def _format_sse(event: dict) -> bytes:
    name = event.get("type", "message")
    data = _json.dumps(event.get("payload", {}), default=str)
    return f"event: {name}\ndata: {data}\n\n".encode("utf-8")


@app.post("/chat")
async def post_chat(req: Request) -> StreamingResponse:
    body = await req.json()
    user_message = body.get("message", "")
    svc = get_service()

    async def gen():
        async for ev in svc.stream_turn(user_message):
            yield _format_sse(ev)

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: Run the SSE test**

Run: `pytest tests/chat/test_app.py::test_chat_sse_streams_envelope -v`
Expected: passes.

- [ ] **Step 5: Run the entire chat test suite**

Run: `pytest tests/chat/ -v -k "not static_index"`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```
git add logic/chat/app.py tests/chat/test_app.py
git commit -m "feat: /chat SSE endpoint streams envelope events to the browser"
```

---

### Task 13: Frontend — index.html + chat.css skeleton

**Files:**
- Create: `ui/chat/index.html`
- Create: `ui/chat/chat.css`

- [ ] **Step 1: Create `ui/chat/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>ERP Chat</title>
  <link rel="stylesheet" href="chat.css" />
  <script src="https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.5/dist/purify.min.js"></script>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body>
  <header>
    <h1>ERP Chat</h1>
    <button id="new-chat">New chat</button>
  </header>
  <main id="messages" aria-live="polite"></main>
  <footer>
    <button id="mic" title="Hold to speak" hidden>🎙️</button>
    <textarea id="input" rows="1" placeholder="Ask a question…"></textarea>
    <button id="send">Send</button>
  </footer>
  <script type="module" src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `ui/chat/chat.css`**

```css
:root {
  --bg: #fafafa;
  --fg: #1a1a1a;
  --muted: #666;
  --accent: #2b6cb0;
  --bubble-user: #dbeafe;
  --bubble-asst: #ffffff;
  --border: #e2e8f0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, sans-serif;
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg); }
body { display: grid; grid-template-rows: auto 1fr auto; max-width: 880px; margin: 0 auto; }
header { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; border-bottom: 1px solid var(--border); }
header h1 { margin: 0; font-size: 18px; }
#new-chat { background: transparent; border: 1px solid var(--border); padding: 6px 10px; border-radius: 6px; cursor: pointer; }
main { overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px; }
footer { display: flex; gap: 8px; padding: 12px 16px; border-top: 1px solid var(--border); background: #fff; }
#input { flex: 1; resize: none; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; font: inherit; }
#send, #mic { padding: 8px 14px; border: 1px solid var(--border); background: #fff; border-radius: 8px; cursor: pointer; }
.msg { padding: 10px 14px; border-radius: 10px; max-width: 90%; }
.msg.user { background: var(--bubble-user); align-self: flex-end; }
.msg.assistant { background: var(--bubble-asst); border: 1px solid var(--border); align-self: flex-start; width: 100%; }
.status { color: var(--muted); font-size: 12px; font-style: italic; }
.error { color: #b91c1c; }
.value-card { padding: 14px 18px; border: 1px solid var(--border); border-radius: 10px; }
.value-card .label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; }
.value-card .value { font-size: 28px; font-weight: 600; }
table { border-collapse: collapse; width: 100%; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); font-size: 14px; }
th { background: #f1f5f9; }
.copy-csv { font-size: 12px; margin-top: 6px; }
.chart { width: 100%; min-height: 320px; }
.report { padding: 12px; border: 1px solid var(--border); border-radius: 10px; }
.report .pdf-link { display: inline-block; margin-top: 8px; font-size: 14px; }
@media print {
  header, footer, #new-chat { display: none; }
  main { overflow: visible; }
}
```

- [ ] **Step 3: Run the static-index test now that the file exists**

Run: `pytest tests/chat/test_app.py::test_static_index_served -v`
Expected: passes.

- [ ] **Step 4: Commit**

```
git add ui/chat/index.html ui/chat/chat.css
git commit -m "feat: chat UI skeleton (HTML + CSS)"
```

---

### Task 14: Frontend — `sse.js` + `app.js` wiring with text rendering

**Files:**
- Create: `ui/chat/sse.js`
- Create: `ui/chat/app.js`
- Create: `ui/chat/renderers/text.js`

- [ ] **Step 1: Implement `ui/chat/sse.js` (POST-supporting SSE client)**

```js
// Minimal SSE-over-fetch reader. Yields {event, data} objects.
export async function* streamSse(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    throw new Error(`SSE request failed: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      const event = parseChunk(chunk);
      if (event) yield event;
    }
  }
}

function parseChunk(chunk) {
  let event = "message";
  let data = "";
  for (const line of chunk.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try { return { event, data: JSON.parse(data) }; } catch { return { event, data }; }
}
```

- [ ] **Step 2: Implement `ui/chat/renderers/text.js`**

```js
export function renderText(block) {
  const div = document.createElement("div");
  const html = window.marked.parse(block.markdown || "");
  div.innerHTML = window.DOMPurify.sanitize(html);
  return div;
}
```

- [ ] **Step 3: Implement `ui/chat/app.js` (wiring; only text renderer for now)**

```js
import { streamSse } from "./sse.js";
import { renderText } from "./renderers/text.js";

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const newChatBtn = document.getElementById("new-chat");

const RENDERERS = {
  text: renderText,
  // value, table, chart, report — added in Task 15
};

function addMessage(role) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  messagesEl.appendChild(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

function addStatus(parent, phase, sql) {
  const s = document.createElement("div");
  s.className = "status";
  s.textContent = phase === "querying" ? `Running query: ${sql.slice(0, 80)}…` : "Thinking…";
  parent.appendChild(s);
  return s;
}

function addError(parent, msg) {
  const e = document.createElement("div");
  e.className = "error";
  e.textContent = `Error: ${msg}`;
  parent.appendChild(e);
}

async function send() {
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = "";
  const userEl = addMessage("user");
  userEl.textContent = text;
  const asstEl = addMessage("assistant");
  let lastStatus = null;
  try {
    for await (const ev of streamSse("/chat", { message: text })) {
      if (ev.event === "status") {
        if (lastStatus) lastStatus.remove();
        lastStatus = addStatus(asstEl, ev.data.phase, ev.data.sql || "");
      } else if (ev.event === "block") {
        if (lastStatus) { lastStatus.remove(); lastStatus = null; }
        const fn = RENDERERS[ev.data.kind];
        if (fn) asstEl.appendChild(fn(ev.data));
        else asstEl.appendChild(document.createTextNode(`[unsupported block: ${ev.data.kind}]`));
      } else if (ev.event === "citation") {
        // wired in Task 15 if needed
      } else if (ev.event === "error") {
        if (lastStatus) { lastStatus.remove(); lastStatus = null; }
        addError(asstEl, ev.data.message || "unknown");
      } else if (ev.event === "done") {
        if (lastStatus) { lastStatus.remove(); lastStatus = null; }
      }
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }
  } catch (e) {
    addError(asstEl, e.message);
  }
}

sendBtn.addEventListener("click", send);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
newChatBtn.addEventListener("click", async () => {
  await fetch("/chat/reset", { method: "POST" });
  messagesEl.innerHTML = "";
});
```

- [ ] **Step 4: Manual verification**

Run: `uvicorn logic.chat.app:app --reload --port 8000`
Open `http://localhost:8000/` in Chrome.
Type "say hi". Expected: a "thinking…" status, then a single text bubble with Claude's reply. Stop the server.

(If `ANTHROPIC_API_KEY` is not set, you'll get an error in the assistant bubble — that's fine; the wiring is verified.)

- [ ] **Step 5: Commit**

```
git add ui/chat/sse.js ui/chat/app.js ui/chat/renderers/text.js
git commit -m "feat: chat UI wiring with SSE + text block renderer"
```

---

### Task 15: Frontend — value / table / chart / report renderers

**Files:**
- Create: `ui/chat/renderers/value.js`
- Create: `ui/chat/renderers/table.js`
- Create: `ui/chat/renderers/chart.js`
- Create: `ui/chat/renderers/report.js`
- Modify: `ui/chat/app.js`

- [ ] **Step 1: `ui/chat/renderers/value.js`**

```js
export function renderValue(block) {
  const card = document.createElement("div");
  card.className = "value-card";
  const label = document.createElement("div");
  label.className = "label";
  label.textContent = block.label;
  const value = document.createElement("div");
  value.className = "value";
  const formatted = typeof block.value === "number"
    ? block.value.toLocaleString()
    : String(block.value);
  value.textContent = block.unit ? `${formatted} ${block.unit}` : formatted;
  card.append(label, value);
  return card;
}
```

- [ ] **Step 2: `ui/chat/renderers/table.js`**

```js
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
```

- [ ] **Step 3: `ui/chat/renderers/chart.js`**

```js
export function renderChart(block) {
  const wrap = document.createElement("div");
  const title = document.createElement("div");
  title.className = "status";
  title.textContent = block.title;
  const chart = document.createElement("div");
  chart.className = "chart";
  wrap.append(title, chart);
  // Plotly is loaded as a global from the CDN script tag.
  queueMicrotask(() => {
    window.Plotly.newPlot(chart, block.plotly.data || [], block.plotly.layout || {}, { responsive: true });
  });
  return wrap;
}
```

- [ ] **Step 4: `ui/chat/renderers/report.js`**

```js
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
```

- [ ] **Step 5: Wire renderers into `ui/chat/app.js`**

Edit `ui/chat/app.js` — replace the import block and the `RENDERERS` constant:

```js
import { streamSse } from "./sse.js";
import { renderText } from "./renderers/text.js";
import { renderValue } from "./renderers/value.js";
import { renderTable } from "./renderers/table.js";
import { renderChart } from "./renderers/chart.js";
import { renderReport } from "./renderers/report.js";
```

```js
const RENDERERS = {
  text: renderText,
  value: renderValue,
  table: renderTable,
  chart: renderChart,
  report: renderReport,
};
```

- [ ] **Step 6: Manual verification**

Run: `uvicorn logic.chat.app:app --reload --port 8000` and open the browser. Ask:

1. "Give me a value block with label 'pi' and value 3.14" → value card.
2. "Give me a table with columns a,b and rows [1,2],[3,4]" → table with Copy CSV.
3. "Give me a chart titled t with a single trace y=[1,2,3]" → Plotly chart renders.
4. "Give me a one-paragraph report titled Hello" → report block + Download PDF link.

(Claude may refuse to fabricate these without DB context — that's OK for visual verification; rephrase to nudge it.) Stop the server.

- [ ] **Step 7: Commit**

```
git add ui/chat/renderers ui/chat/app.js
git commit -m "feat: value/table/chart/report renderers wired into chat UI"
```

---

### Task 16: Frontend — voice input via Web Speech API

**Files:**
- Create: `ui/chat/voice.js`
- Modify: `ui/chat/app.js`

- [ ] **Step 1: `ui/chat/voice.js`**

```js
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

export function isAvailable() {
  return typeof SR !== "undefined";
}

export function createRecognizer(lang) {
  const r = new SR();
  r.lang = lang || "pt-PT";
  r.continuous = false;
  r.interimResults = false;
  return r;
}
```

- [ ] **Step 2: Wire the mic button into `ui/chat/app.js`**

Append to `ui/chat/app.js`:

```js
import { isAvailable, createRecognizer } from "./voice.js";

const micBtn = document.getElementById("mic");

(async function setupVoice() {
  if (!isAvailable()) return;
  const cfg = await fetch("/config").then(r => r.json()).catch(() => ({ voice_lang: "pt-PT" }));
  const rec = createRecognizer(cfg.voice_lang);
  micBtn.hidden = false;
  let listening = false;
  micBtn.addEventListener("click", () => {
    if (listening) { rec.stop(); return; }
    listening = true;
    micBtn.textContent = "⏹";
    rec.start();
  });
  rec.addEventListener("result", (ev) => {
    const t = ev.results[0][0].transcript;
    inputEl.value = (inputEl.value ? inputEl.value + " " : "") + t;
  });
  rec.addEventListener("end", () => {
    listening = false;
    micBtn.textContent = "🎙️";
  });
  rec.addEventListener("error", () => {
    listening = false;
    micBtn.textContent = "🎙️";
  });
})();
```

- [ ] **Step 3: Manual verification**

In Chrome / Edge: load the page → mic icon appears → click it → speak a short Portuguese (or your `CHAT_VOICE_LANG`) sentence → the input field fills with the transcript. In Firefox (no Web Speech): the mic button stays hidden. Typing still works in both.

- [ ] **Step 4: Commit**

```
git add ui/chat/voice.js ui/chat/app.js
git commit -m "feat: voice input via Web Speech API (graceful when unavailable)"
```

---

### Task 17: Manual end-to-end smoke + README note + final commit

**Files:**
- Modify: `CLAUDE.md` (add a short "Running the chat UI" subsection under "Tech Stack" or near `uvicorn` mention)

- [ ] **Step 1: Run the full backend test suite once more**

Run: `pytest tests/chat/ -v`
Expected: all tests pass.

- [ ] **Step 2: Smoke-test against the real DB**

Set `DATABASE_URL` to a **read-only** SQL Server login pointing at DevDB. Set `ANTHROPIC_API_KEY`. Start: `uvicorn logic.chat.app:app --reload --port 8000`.

Walk through these four queries in order, in a single conversation (no "New chat" between them):

1. "How many invoices are there in 2026?" → expect a single `value` block. Verify `logs/queries.jsonl` got one row.
2. "Top 10 customers by revenue in 2026." → expect a `table` block with 10 rows and Copy CSV working.
3. "Monthly revenue trend for 2026." → expect a `chart` block (Plotly renders).
4. "Sales summary for Q1 2026 — short report." → expect a `report` block. Click "Download PDF" — expect either a PDF download (if WeasyPrint is installed) or the friendly fallback alert (if not).

Note any issues; fix them before continuing. Document any flakiness or unexpected behaviour as TODOs in a follow-up file (do not leave inline TODOs in code).

- [ ] **Step 3: Add a "Running the chat UI" subsection to CLAUDE.md**

In `CLAUDE.md`, find the "Tech Stack" section and append (after the existing `uvicorn logic.main:app --reload` note — note that line is outdated; do not modify it; just add the new lines below it):

```
Run the chat UI server: `uvicorn logic.chat.app:app --reload`, then open http://localhost:8000/.
The chat UI requires `ANTHROPIC_API_KEY` and a `DATABASE_URL` pointing at a read-only SQL Server login.
```

- [ ] **Step 4: Commit**

```
git add CLAUDE.md
git commit -m "docs: note how to run the chat UI in CLAUDE.md"
```

- [ ] **Step 5: Verify final state**

Run: `git log --oneline -20`
Expected: the new feature lands across ~17 atomic commits, each named meaningfully.

Run: `pytest tests/` (full suite).
Expected: all existing payroll tests still pass; all new chat tests pass.

---

## Self-review checklist (already applied)

- **Spec coverage:** Every section of the spec is implemented by at least one task:
  - §3 (UX) → Tasks 13–16
  - §4 (architecture) → Tasks 10–12
  - §5.1 (FastAPI) → Tasks 11, 12
  - §5.2 (ChatService) → Task 10
  - §5.3 (schema_context) → Task 7
  - §5.4 (sql_executor) → Tasks 5, 6
  - §5.5 (audit) → Task 4
  - §5.6 (envelope) → Task 3
  - §5.7 (pdf) → Task 9
  - §5.8 (prompts) → Task 8
  - §6 (SSE protocol) → Tasks 10, 12
  - §7 (frontend) → Tasks 13–16
  - §8 (config) → Task 1, Task 11
  - §9 (testing) → every task is TDD; manual smoke in Task 17
- **No placeholders:** Every step has concrete code; commands have expected outputs.
- **Type consistency:** `ClaudeEnvelope` / `RawReportBlock` / `ReportBlock` consistent across Tasks 3 → 10 → 15. `QueryResult` / `QueryError` consistent across Tasks 5 → 6 → 10.
