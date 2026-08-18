# Bills Service Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the bill ingestion service on Render behind a password, with an audit row written inside the same transaction as the document it records.

**Architecture:** Chat's HTTP Basic middleware moves to `logic/common/password_gate.py` and both apps install it with their own secret. The bills audit gains a SQL Server table, written by `db/bills_audit.py` on a session handed in by `write_executor` — so the audit row commits or rolls back with the document. One Dockerfile serves two Render services differing only by `dockerCommand`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core, pytest, Docker, Render Blueprint.

**Spec:** [docs/superpowers/specs/2026-08-18-bills-service-deployment-design.md](../specs/2026-08-18-bills-service-deployment-design.md)

## Global Constraints

- **A `None` or empty password installs no middleware at all.** Local development and the whole existing test suite run ungated; only the deployed services set the env var. Breaking this breaks every test in the repo.
- `/healthz` must be **exempt from the gate** (Render's health check is unauthenticated) and **registered before the `StaticFiles` mount at `/`** in the bills app, or the UI catch-all swallows it.
- Only the **password half** of the HTTP Basic credential is checked; the username is ignored. Comparison uses `secrets.compare_digest`.
- Bills uses `BILLS_APP_PASSWORD`, never `APP_PASSWORD`. Separate secrets are the point.
- **The success audit insert must NOT be swallowed.** It runs inside the document's transaction, so if it raises, the whole write rolls back. That is the atomic guarantee: no document without its audit row.
- Audit column names are **module constants**, never caller-derived — the same SQL-identifier-safety invariant `write_executor._check_columns` already enforces.
- The JSONL file mirror stays best-effort with exceptions swallowed, exactly as today.
- No new package dependencies.
- Interpreter: `C:/Users/joaog/erp_venv/Scripts/python.exe` — the repo's `.venv` is corrupted by OneDrive sync.
- Baseline before this work: `tests/bills/` is **160 passed, 1 xfailed**. `tests/chat/` has **21 pre-existing failures** unrelated to this work — do not try to fix them, but do not add to them either.

## File Structure

| File | Responsibility |
|---|---|
| `logic/common/__init__.py` (create) | Package marker |
| `logic/common/password_gate.py` (create) | The shared HTTP Basic middleware |
| `logic/chat/app.py` (modify) | Installs the gate instead of defining it |
| `logic/bills/app.py` (modify) | Installs the gate; adds `/healthz` |
| `db/migrations/002_bills_audit.sql` (create) | Audit table DDL |
| `db/bills_audit.py` (create) | Parameterised audit INSERT on a given session |
| `logic/bills/audit_writer.py` (modify) | Builds the entry; `insert` and `record_failure` |
| `logic/bills/write_executor.py` (modify) | Writes the audit row inside its transaction |
| `logic/bills/service.py` (modify) | Passes operator/audit through; failure path |
| `Dockerfile` (modify) | Tesseract + Poppler in the apt layer |
| `render.yaml` (modify) | Second service, `erp-bills` |
| `tests/common/test_password_gate.py` (create) | Gate behaviour, exhaustively |
| `tests/bills/test_app.py` (modify) | `/healthz`, and the gate wired to bills |
| `tests/bills/test_bills_audit_sql.py` (create) | The INSERT's shape and parameters |
| `tests/bills/test_audit_writer.py` (modify) | `insert` / `record_failure` behaviour |
| `tests/bills/test_write_executor.py` (modify) | Audit row on the same session |
| `tests/bills/test_service.py` (modify) | Fakes updated for the new signatures |

---

### Task 1: The shared password gate

**Files:**
- Create: `logic/common/__init__.py`, `logic/common/password_gate.py`
- Test: `tests/common/__init__.py`, `tests/common/test_password_gate.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `install_password_gate(app, password: str | None, *, realm: str, exempt: Iterable[str] = frozenset({"/healthz"})) -> None`. Tasks 2 and 3 call it.

- [ ] **Step 1: Write the failing test**

Create `tests/common/__init__.py` (empty) and `tests/common/test_password_gate.py`:

```python
import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from logic.common.password_gate import install_password_gate


def _app(password, **kw):
    app = FastAPI()

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/private")
    def private():
        return {"secret": True}

    install_password_gate(app, password, realm="Test Realm", **kw)
    return TestClient(app)


def _auth(user, pw):
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.mark.parametrize("password", [None, ""])
def test_no_password_installs_no_gate(password):
    # Local dev and the whole existing test suite depend on this.
    client = _app(password)
    assert client.get("/private").status_code == 200


def test_missing_credentials_are_rejected():
    r = _app("s3cret").get("/private")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == 'Basic realm="Test Realm"'


def test_wrong_password_is_rejected():
    r = _app("s3cret").get("/private", headers=_auth("someone", "wrong"))
    assert r.status_code == 401


def test_correct_password_passes():
    r = _app("s3cret").get("/private", headers=_auth("someone", "s3cret"))
    assert r.status_code == 200


def test_username_is_ignored():
    # The deployment shares one secret rather than issuing accounts.
    client = _app("s3cret")
    for user in ("", "alice", "root"):
        assert client.get("/private", headers=_auth(user, "s3cret")).status_code == 200


def test_healthz_is_exempt_by_default():
    # Render's health check is unauthenticated; a 401 here means the service
    # never goes live.
    assert _app("s3cret").get("/healthz").status_code == 200


def test_exempt_paths_are_configurable():
    client = _app("s3cret", exempt={"/private"})
    assert client.get("/private").status_code == 200
    assert client.get("/healthz").status_code == 401


@pytest.mark.parametrize("header", [
    "Bearer abc", "Basic", "Basic !!!not-base64!!!", "Basic " + base64.b64encode(b"no-colon").decode(),
])
def test_malformed_authorization_headers_are_rejected_without_raising(header):
    r = _app("s3cret").get("/private", headers={"Authorization": header})
    assert r.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/common/test_password_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.common'`

- [ ] **Step 3: Write minimal implementation**

Create `logic/common/__init__.py` (empty), and `logic/common/password_gate.py`:

```python
from __future__ import annotations

import base64
import secrets
from collections.abc import Iterable

from fastapi import FastAPI, Request, Response

_DEFAULT_EXEMPT = frozenset({"/healthz"})


def install_password_gate(app: FastAPI, password: str | None, *, realm: str,
                          exempt: Iterable[str] = _DEFAULT_EXEMPT) -> None:
    """Put a shared-password HTTP Basic gate in front of every path but `exempt`.

    Only the password half of the credential is checked and the username is
    ignored: the deployment shares one secret rather than issuing accounts.

    An unset password installs NO middleware at all, so local development and
    the test suite run ungated while the deployed services set the env var."""
    if not password:
        return
    exempt_paths = frozenset(exempt)

    @app.middleware("http")
    async def _basic_auth(request: Request, call_next):
        if request.url.path in exempt_paths or _authorized(
                request.headers.get("Authorization", ""), password):
            return await call_next(request)
        return Response(status_code=401,
                        headers={"WWW-Authenticate": f'Basic realm="{realm}"'})


def _authorized(header: str, password: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        _, _, supplied = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False  # malformed base64 or non-UTF-8 is simply not authorized
    return secrets.compare_digest(supplied, password)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/common/test_password_gate.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add logic/common tests/common
git commit -m "feat(common): shared password gate middleware"
```

---

### Task 2: Chat uses the shared gate

A behaviour-preserving refactor. Chat's existing tests are the evidence.

**Files:**
- Modify: `logic/chat/app.py` (the `_APP_PASSWORD` constant and the `_basic_auth` middleware, around lines 84–104)

**Interfaces:**
- Consumes: `install_password_gate` (Task 1).
- Produces: nothing new.

- [ ] **Step 1: Record the baseline**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/chat/ -q`
Record the pass/fail counts. There are **21 pre-existing failures** unrelated to this work; the number must not change.

- [ ] **Step 2: Replace the middleware**

In `logic/chat/app.py`, delete the `_APP_PASSWORD` assignment and the whole
`@app.middleware("http")` / `async def _basic_auth(...)` block, and put in their place:

```python
# Shared-password gate for public deployment. Unset APP_PASSWORD (local dev)
# installs no gate at all.
install_password_gate(app, os.environ.get("APP_PASSWORD"), realm="ERP Chat")
```

Add the import alongside the other `logic.` imports:

```python
from logic.common.password_gate import install_password_gate
```

- [ ] **Step 3: Remove imports your change orphaned**

Run: `grep -n "base64\.\|secrets\." logic/chat/app.py`

`secrets` is still used by `_session_id` — keep it. Remove `import base64` **only if** the
grep shows no remaining `base64.` use. Do not remove anything else.

- [ ] **Step 4: Verify the refactor changed nothing**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/chat/ -q`
Expected: exactly the counts from Step 1.

Then confirm the gate still functions, since chat's tests may not cover it:

```bash
C:/Users/joaog/erp_venv/Scripts/python.exe -c "
import os; os.environ['APP_PASSWORD']='s3cret'
import importlib, logic.chat.app as m; m = importlib.reload(m)
from fastapi.testclient import TestClient
c = TestClient(m.app)
print('healthz:', c.get('/healthz').status_code)
print('gated  :', c.get('/conversations').status_code)
"
```
Expected: `healthz: 200` and `gated  : 401`.

- [ ] **Step 5: Commit**

```bash
git add logic/chat/app.py
git commit -m "refactor(chat): use the shared password gate"
```

---

### Task 3: Gate the bills app and give it a health check

**Files:**
- Modify: `logic/bills/app.py`
- Test: `tests/bills/test_app.py` (append)

**Interfaces:**
- Consumes: `install_password_gate` (Task 1).
- Produces: a `/healthz` route on the bills app.

- [ ] **Step 1: Write the failing test**

Append to `tests/bills/test_app.py`:

```python
import importlib


def test_healthz_answers_without_credentials(monkeypatch):
    client = _client(monkeypatch)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_bills_app_is_gated_when_the_password_is_set(monkeypatch):
    """The service that writes to ForumSI must not be open to the internet.

    The gate is installed at import time from the environment, so the module is
    reloaded with the variable set, then reloaded again afterwards to keep a
    gated app from leaking into the other tests in this file.
    """
    monkeypatch.setenv("BILLS_APP_PASSWORD", "s3cret")
    import logic.bills.app as appmod
    gated = importlib.reload(appmod)
    try:
        client = TestClient(gated.app)
        # Health check stays open, or Render never marks the service live.
        assert client.get("/healthz").status_code == 200
        r = client.post("/bills/operator", json={"name": "alice"})
        assert r.status_code == 401
        assert r.headers["WWW-Authenticate"] == 'Basic realm="Bill Ingestion"'
    finally:
        monkeypatch.delenv("BILLS_APP_PASSWORD", raising=False)
        importlib.reload(gated)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_app.py -v`
Expected: FAIL — `/healthz` returns 404 (the `StaticFiles` mount handles it), and the gated
test gets 200 instead of 401.

- [ ] **Step 3: Write minimal implementation**

In `logic/bills/app.py`, add the import beside the other `logic.` imports:

```python
from logic.common.password_gate import install_password_gate
```

Immediately after `app = FastAPI(title="Bill Ingestion")`, add:

```python
# This service writes to the ForumSI database, so it is gated whenever
# BILLS_APP_PASSWORD is set. Unset (local dev) installs no gate. The secret is
# deliberately separate from the chat service's APP_PASSWORD.
install_password_gate(app, os.environ.get("BILLS_APP_PASSWORD"),
                      realm="Bill Ingestion")


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok"}
```

The `/healthz` route must sit **above** the `app.mount("/", StaticFiles(...))` call at the
bottom of the file — a mount at `/` matches anything not already routed.

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ -q`
Expected: PASS — the whole bills suite, 160 pre-existing plus 2 new, 1 xfailed.

- [ ] **Step 5: Commit**

```bash
git add logic/bills/app.py tests/bills/test_app.py
git commit -m "feat(bills): password-gate the service and add a health check"
```

---

### Task 4: The audit table and its INSERT

**Files:**
- Create: `db/migrations/002_bills_audit.sql`, `db/bills_audit.py`
- Test: `tests/bills/test_bills_audit_sql.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `db.bills_audit.insert_audit(session, entry: dict, *, table_prefix: str = "") -> None` and the module constant `TABLE = "ERPAgent_BillAudit"`. Task 5 calls it.

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_bills_audit_sql.py`:

```python
import json

from db.bills_audit import TABLE, insert_audit


class FakeSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))


ENTRY = {
    "ts": "2026-08-18T09:00:00.000Z", "kind": "bill_ingest", "operator": "alice",
    "proposal_id": "bill_abc123", "document_chave": 99, "supplier_chave": 7,
    "line_chaves": [1, 2], "created_supplier": False, "created_articles": [],
    "rule_doc": "purchase_invoice", "rule_version": "1.0", "status": "ok",
}


def test_insert_uses_the_audit_table_with_the_prefix():
    s = FakeSession()
    insert_audit(s, ENTRY, table_prefix="ForumSI.dbo.")
    sql, _ = s.calls[0]
    assert f"INSERT INTO ForumSI.dbo.{TABLE}" in sql


def test_insert_binds_every_column_as_a_parameter():
    s = FakeSession()
    insert_audit(s, ENTRY)
    sql, params = s.calls[0]
    # No entry value may be interpolated into the statement text.
    assert "alice" not in sql and "bill_abc123" not in sql
    assert params["Operator"] == "alice"
    assert params["ProposalId"] == "bill_abc123"
    assert params["DocumentChave"] == 99
    assert params["SupplierChave"] == 7
    assert params["Status"] == "ok"
    assert params["Ts"] == "2026-08-18T09:00:00.000Z"


def test_payload_carries_the_whole_entry_as_json():
    # Fields not given their own column still survive, so adding one later
    # costs no migration.
    s = FakeSession()
    insert_audit(s, ENTRY)
    _, params = s.calls[0]
    assert json.loads(params["Payload"])["line_chaves"] == [1, 2]
    assert json.loads(params["Payload"])["created_supplier"] is False


def test_a_failure_entry_with_no_result_still_inserts():
    s = FakeSession()
    insert_audit(s, {"ts": "t", "operator": "bob", "proposal_id": "p",
                     "status": "error", "rule_doc": "d", "rule_version": "1"})
    _, params = s.calls[0]
    assert params["Status"] == "error"
    assert params["DocumentChave"] is None


def test_entry_keys_never_reach_the_statement_text():
    # The column list is a module constant; a hostile key must not become SQL.
    s = FakeSession()
    insert_audit(s, {**ENTRY, "Payload); DROP TABLE x--": "evil"})
    sql, _ = s.calls[0]
    assert "DROP TABLE" not in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_bills_audit_sql.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'db.bills_audit'`

- [ ] **Step 3: Write minimal implementation**

Create `db/migrations/002_bills_audit.sql`:

```sql
-- Audit trail for bill ingestion writes.
--
-- Lives in the database reached by BILLS_WRITE_DATABASE_URL, not somewhere
-- tidier, because the row is inserted inside the same transaction as the
-- document it records: either both land or neither.
--
-- Payload holds the whole audit entry as JSON, so adding a field later needs no
-- migration; the promoted columns exist only to make the common queries cheap.
IF OBJECT_ID('dbo.ERPAgent_BillAudit', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.ERPAgent_BillAudit (
        Id            BIGINT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        Ts            NVARCHAR(32)   NOT NULL,
        Operator      NVARCHAR(128)  NOT NULL,
        ProposalId    NVARCHAR(64)   NOT NULL,
        Status        NVARCHAR(16)   NOT NULL,
        DocumentChave INT            NULL,
        SupplierChave INT            NULL,
        RuleDoc       NVARCHAR(128)  NULL,
        RuleVersion   NVARCHAR(32)   NULL,
        Payload       NVARCHAR(MAX)  NOT NULL
    );
    CREATE INDEX IX_ERPAgent_BillAudit_Ts ON dbo.ERPAgent_BillAudit (Ts DESC);
    CREATE INDEX IX_ERPAgent_BillAudit_Doc ON dbo.ERPAgent_BillAudit (DocumentChave);
END
```

`Ts` is `NVARCHAR(32)` rather than `DATETIME2` deliberately: `AuditLog.now_iso()` already
produces a sortable ISO-8601 UTC string, and storing it verbatim keeps the column identical to
the JSONL mirror's value with no driver-dependent conversion in between.

Create `db/bills_audit.py`:

```python
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

TABLE = "ERPAgent_BillAudit"

# Module constants, never derived from the entry: an audit entry is caller
# influenced, and nothing caller-influenced may reach an SQL identifier
# position. Same invariant write_executor._check_columns enforces.
_COLUMNS = ("Ts", "Operator", "ProposalId", "Status", "DocumentChave",
            "SupplierChave", "RuleDoc", "RuleVersion", "Payload")


def insert_audit(session, entry: dict[str, Any], *, table_prefix: str = "") -> None:
    """Insert one audit row on the session it is handed.

    Takes a session rather than opening one so the caller can put this inside
    the document's own transaction — the audit row and the document it records
    then commit or roll back together."""
    row = {
        "Ts": entry.get("ts"),
        "Operator": entry.get("operator"),
        "ProposalId": entry.get("proposal_id"),
        "Status": entry.get("status"),
        "DocumentChave": entry.get("document_chave"),
        "SupplierChave": entry.get("supplier_chave"),
        "RuleDoc": entry.get("rule_doc"),
        "RuleVersion": entry.get("rule_version"),
        "Payload": json.dumps(entry, separators=(",", ":"), default=str),
    }
    cols = ", ".join(_COLUMNS)
    binds = ", ".join(f":{c}" for c in _COLUMNS)
    session.execute(
        text(f"INSERT INTO {table_prefix}{TABLE} ({cols}) VALUES ({binds})"), row)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_bills_audit_sql.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add db/bills_audit.py db/migrations/002_bills_audit.sql tests/bills/test_bills_audit_sql.py
git commit -m "feat(db): audit table and parameterised insert for bill writes"
```

---

### Task 5: The audit writer gains a database sink

**Files:**
- Modify: `logic/bills/audit_writer.py`
- Test: `tests/bills/test_audit_writer.py`

**Interfaces:**
- Consumes: `insert_audit` (Task 4).
- Produces: `BillAuditWriter(audit, *, session_factory=None, table_prefix="")` with
  `insert(session, *, operator, plan, result, status) -> None` and
  `record_failure(*, operator, plan, result, status) -> None`. The old `record` is gone.
  Task 6 calls both.

- [ ] **Step 1: Write the failing test**

Replace the contents of `tests/bills/test_audit_writer.py` with:

```python
from contextlib import contextmanager

import pytest

from logic.bills.audit_writer import BillAuditWriter
from logic.bills.models import MatchResult, WritePlan


class FakeFileAudit:
    def __init__(self):
        self.entries = []

    def append(self, entry):
        self.entries.append(entry)


class FakeSession:
    def __init__(self, fail=False):
        self.calls = []
        self._fail = fail

    def execute(self, statement, params=None):
        if self._fail:
            raise RuntimeError("db is down")
        self.calls.append((str(statement), params))


def _factory(session):
    @contextmanager
    def factory():
        yield session
    return factory


def _plan():
    return WritePlan(proposal_id="bill_abc", supplier=MatchResult(status="matched", chave=7),
                     header={}, lines=[], rule_doc="purchase_invoice", rule_version="1.0")


RESULT = {"document_chave": 99, "supplier_chave": 7, "line_chaves": [1],
          "created_supplier": False, "created_articles": []}


def test_insert_writes_the_row_on_the_session_it_is_given():
    file_audit, session = FakeFileAudit(), FakeSession()
    BillAuditWriter(file_audit).insert(session, operator="alice", plan=_plan(),
                                       result=RESULT, status="ok")
    assert len(session.calls) == 1
    _, params = session.calls[0]
    assert params["Operator"] == "alice"
    assert params["DocumentChave"] == 99


def test_insert_also_mirrors_to_the_file():
    file_audit, session = FakeFileAudit(), FakeSession()
    BillAuditWriter(file_audit).insert(session, operator="alice", plan=_plan(),
                                       result=RESULT, status="ok")
    assert file_audit.entries[0]["kind"] == "bill_ingest"
    assert file_audit.entries[0]["operator"] == "alice"


def test_insert_does_not_swallow_a_failed_audit_write():
    """The atomic guarantee: if the audit row cannot be written, the whole
    transaction must roll back rather than leave an unaudited document."""
    writer = BillAuditWriter(FakeFileAudit())
    with pytest.raises(RuntimeError):
        writer.insert(FakeSession(fail=True), operator="alice", plan=_plan(),
                      result=RESULT, status="ok")


def test_record_failure_opens_its_own_session():
    # The write transaction has already rolled back by the time a failure is
    # known, so the failure row cannot ride on it.
    file_audit, session = FakeFileAudit(), FakeSession()
    BillAuditWriter(file_audit, session_factory=_factory(session)).record_failure(
        operator="bob", plan=_plan(), result={}, status="error")
    assert len(session.calls) == 1
    assert session.calls[0][1]["Status"] == "error"
    assert file_audit.entries[0]["status"] == "error"


def test_record_failure_falls_back_to_the_file_when_the_db_is_also_down():
    # Usually the DB is down precisely because that is why the write failed;
    # masking the original error with this one would be worse than useless.
    file_audit = FakeFileAudit()
    writer = BillAuditWriter(file_audit, session_factory=_factory(FakeSession(fail=True)))
    writer.record_failure(operator="bob", plan=_plan(), result={}, status="error")
    assert file_audit.entries[0]["status"] == "error"


def test_record_failure_without_a_factory_still_mirrors_to_the_file():
    file_audit = FakeFileAudit()
    BillAuditWriter(file_audit).record_failure(operator="bob", plan=_plan(),
                                               result={}, status="error")
    assert file_audit.entries[0]["operator"] == "bob"


def test_entry_keeps_its_existing_shape():
    file_audit, session = FakeFileAudit(), FakeSession()
    BillAuditWriter(file_audit).insert(session, operator="alice", plan=_plan(),
                                       result=RESULT, status="ok")
    entry = file_audit.entries[0]
    assert set(entry) == {"ts", "kind", "operator", "proposal_id", "document_chave",
                          "supplier_chave", "line_chaves", "created_supplier",
                          "created_articles", "rule_doc", "rule_version", "status"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_audit_writer.py -v`
Expected: FAIL — `BillAuditWriter` has no attribute `insert`.

- [ ] **Step 3: Write minimal implementation**

Replace `logic/bills/audit_writer.py` with:

```python
from __future__ import annotations

import logging
from typing import Any, Callable

from db.bills_audit import insert_audit
from logic.bills.models import WritePlan
from logic.chat.audit import AuditLog

_log = logging.getLogger(__name__)


class BillAuditWriter:
    """Builds the audit entry and puts it where it survives a restart.

    The database row is the record of truth. The JSONL file is a mirror: an
    on-box diagnostic, and the surviving copy if the INSERT itself fails."""

    def __init__(self, audit: AuditLog, *, session_factory: Callable | None = None,
                 table_prefix: str = "") -> None:
        self._audit = audit
        self._factory = session_factory
        self._prefix = table_prefix

    def _entry(self, *, operator: str, plan: WritePlan, result: dict,
               status: str) -> dict[str, Any]:
        return {
            "ts": AuditLog.now_iso(),
            "kind": "bill_ingest",
            "operator": operator,
            "proposal_id": plan.proposal_id,
            "document_chave": result.get("document_chave"),
            "supplier_chave": result.get("supplier_chave"),
            "line_chaves": result.get("line_chaves"),
            "created_supplier": result.get("created_supplier"),
            "created_articles": result.get("created_articles"),
            "rule_doc": plan.rule_doc,
            "rule_version": plan.rule_version,
            "status": status,
        }

    def insert(self, session, *, operator: str, plan: WritePlan, result: dict,
               status: str) -> None:
        """Write the audit row on the caller's session — inside the document's
        own transaction.

        Deliberately does NOT swallow: if the audit row cannot be written, the
        transaction rolls back and no unaudited document is left behind."""
        entry = self._entry(operator=operator, plan=plan, result=result, status=status)
        insert_audit(session, entry, table_prefix=self._prefix)
        self._audit.append(entry)

    def record_failure(self, *, operator: str, plan: WritePlan, result: dict,
                       status: str) -> None:
        """Audit a write that failed. Its transaction has already rolled back,
        so this opens its own session — best-effort, because the database is
        often down precisely because that is why the write failed, and masking
        the original error with this one helps nobody."""
        entry = self._entry(operator=operator, plan=plan, result=result, status=status)
        if self._factory is not None:
            try:
                with self._factory() as session:
                    insert_audit(session, entry, table_prefix=self._prefix)
            except Exception:
                _log.exception("audit row insert failed; entry survives in the file mirror")
        self._audit.append(entry)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_audit_writer.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add logic/bills/audit_writer.py tests/bills/test_audit_writer.py
git commit -m "feat(bills): write the audit entry to the database"
```

---

### Task 6: Write the audit row inside the document's transaction

**Files:**
- Modify: `logic/bills/write_executor.py` (the `execute` method), `logic/bills/service.py` (`commit`), `logic/bills/app.py` (wiring)
- Test: `tests/bills/test_write_executor.py`, `tests/bills/test_service.py`

**Interfaces:**
- Consumes: `BillAuditWriter.insert` / `.record_failure` (Task 5).
- Produces: `BillWriteExecutor.execute(plan, rule, *, operator: str, audit) -> dict` — same return shape, two new **required** keyword arguments.

- [ ] **Step 1: Write the failing test**

`tests/bills/test_write_executor.py` already drives a **real SQLite database** through the
`session_factory` fixture, with helpers `_ex(factory)`, `_plan_matched_supplier()` and
`_rule()`. Reuse them — do not build a parallel set of fakes. Append:

```python
class RecordingAudit:
    """Captures whether the session was inside a transaction at call time."""
    def __init__(self):
        self.calls = []

    def insert(self, session, *, operator, plan, result, status):
        self.calls.append({"in_transaction": session.in_transaction(),
                           "operator": operator, "result": result, "status": status})


class ExplodingAudit:
    def insert(self, session, **kw):
        raise RuntimeError("audit unavailable")


class NullAudit:
    def insert(self, session, **kw):
        pass


def test_audit_is_written_inside_the_document_transaction(session_factory):
    factory, eng = session_factory
    with eng.begin() as c:
        c.execute(text("INSERT INTO Artigos (Chave, Nome) VALUES (42, 'Widget')"))
    audit = RecordingAudit()
    result = _ex(factory).execute(_plan_matched_supplier(), _rule(),
                                  operator="alice", audit=audit)
    assert len(audit.calls) == 1
    call = audit.calls[0]
    assert call["in_transaction"] is True
    assert call["operator"] == "alice"
    assert call["status"] == "ok"
    assert call["result"]["document_chave"] == result["document_chave"]


def test_a_failed_audit_rolls_the_document_back(session_factory):
    """The atomic guarantee stated as a test: if the audit row cannot be
    written, no document may survive. This is the whole point of putting the
    insert inside the transaction rather than after it."""
    factory, eng = session_factory
    with eng.begin() as c:
        c.execute(text("INSERT INTO Artigos (Chave, Nome) VALUES (42, 'Widget')"))
    with pytest.raises(RuntimeError):
        _ex(factory).execute(_plan_matched_supplier(), _rule(),
                             operator="alice", audit=ExplodingAudit())
    with eng.begin() as c:
        assert c.execute(text("SELECT COUNT(*) FROM Doc001")).scalar() == 0
        assert c.execute(text("SELECT COUNT(*) FROM LinDoc001")).scalar() == 0
```

Every pre-existing `execute(...)` call in this file needs the two new keyword arguments —
pass `operator="test", audit=NullAudit()` to each.

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_write_executor.py -v`
Expected: FAIL — `execute() got an unexpected keyword argument 'operator'`.

- [ ] **Step 3: Write minimal implementation**

In `logic/bills/write_executor.py`, change the signature of `execute` to take the two new
required keyword arguments, and replace the bare `return {...}` at the end of the
`with self._factory() as session:` block with:

```python
            result = {"document_chave": doc_pk, "supplier_chave": supplier_chave,
                      "line_chaves": line_chaves, "created_supplier": created_supplier,
                      "created_articles": created_articles}
            # Last statement inside the transaction: the audit row commits with
            # the document or rolls back with it. If this raises, nothing lands.
            audit.insert(session, operator=operator, plan=plan, result=result,
                         status="ok")
            return result
```

In `logic/bills/service.py`, `commit` becomes:

```python
        try:
            result = self._executor.execute(plan, self._rule, operator=operator,
                                            audit=self._audit)
            self._pending.pop(proposal_id)
            return {"status": "ok", **result}
        except Exception as e:  # noqa: BLE001
            self._audit.record_failure(operator=operator, plan=plan,
                                       result={}, status="error")
            return {"status": "error", "message": str(e)[:500]}
```

The previous success-path `self._audit.record(...)` call is deleted — it now happens inside
the transaction.

In `logic/bills/app.py`, give the writer what it needs for the failure path and the prefix:

```python
            audit=BillAuditWriter(AuditLog(_WRITE_LOG_PATH),
                                  session_factory=get_bills_write_session,
                                  table_prefix=_TABLE_PREFIX),
```

- [ ] **Step 4: Update the fakes the signature change broke**

In `tests/bills/test_service.py`, `FakeExecutor.execute` must accept the new keyword
arguments and `FakeAudit` must offer the new methods:

```python
class FakeExecutor:
    def __init__(self): self.calls = []
    def execute(self, plan, rule, *, operator=None, audit=None):
        self.calls.append(plan)
        return {"document_chave": 99, "supplier_chave": 7, "line_chaves": [1],
                "created_supplier": False, "created_articles": []}


class FakeAudit:
    def __init__(self): self.records = []
    def insert(self, session, **kw): self.records.append(kw)
    def record_failure(self, **kw): self.records.append(kw)
```

Then run `grep -rn "\.execute(" tests/bills/ logic/bills/` and fix any remaining call site.

- [ ] **Step 5: Run the full suite and commit**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ -q`
Expected: PASS, 1 xfailed.

```bash
git add logic/bills/write_executor.py logic/bills/service.py logic/bills/app.py tests/bills/test_write_executor.py tests/bills/test_service.py
git commit -m "feat(bills): audit the write inside its own transaction"
```

---

### Task 7: Ship it — Docker, Render, docs

**Files:**
- Modify: `Dockerfile`, `render.yaml`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: no code interface.

- [ ] **Step 1: Add the OCR binaries to the image**

In `Dockerfile`, extend the existing apt install line to:

```
       msodbcsql18 unixodbc-dev libgssapi-krb5-2 libglib2.0-0 \
       tesseract-ocr tesseract-ocr-por poppler-utils \
```

and add above the `RUN`, with the other explanatory comments:

```
# tesseract-ocr-por is not optional: ocr.pdf_to_text runs Tesseract with
# lang="por+eng" and fails outright if the Portuguese traineddata is absent.
# poppler-utils provides pdftoppm, which pdf2image shells out to.
```

Leave `CMD` on the chat app so a bare `docker run` behaves as it does today.

- [ ] **Step 2: Add the second Render service**

Append to the `services:` list in `render.yaml`:

```yaml
  - type: web
    name: erp-bills
    runtime: docker
    plan: free
    region: frankfurt        # same region as erp-chat
    dockerfilePath: ./Dockerfile
    # Same image as erp-chat; only the entrypoint differs.
    dockerCommand: uvicorn logic.bills.app:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /healthz
    autoDeploy: true
    envVars:
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: DATABASE_URL          # read-only, for supplier/article lookups
        sync: false
      - key: BILLS_WRITE_DATABASE_URL   # writable ForumSI login
        sync: false
      - key: BILLS_APP_PASSWORD    # deliberately not APP_PASSWORD
        sync: false
```

- [ ] **Step 3: Document the new variable**

In `CLAUDE.md`, find the line describing what Bill ingestion requires and add
`BILLS_APP_PASSWORD` to it, noting that the service is ungated when it is unset and that the
deployed service must set it.

- [ ] **Step 4: Verify what can be verified here**

There is no Docker and no SQL Server on this machine, so the image is not built and the
migration is not run. What you can and must check:

```bash
C:/Users/joaog/erp_venv/Scripts/python.exe -c "import yaml,sys; d=yaml.safe_load(open('render.yaml')); n=[s['name'] for s in d['services']]; print(n); sys.exit(0 if 'erp-bills' in n and len(n)==2 else 1)"
grep -n "tesseract-ocr-por\|poppler-utils\|libglib2.0-0" Dockerfile
C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: both service names printed, all three apt packages present, and the bills suite
green with `tests/chat/`'s 21 pre-existing failures unchanged.

State in your report, explicitly, that the Docker build and the SQL migration were **not**
executed and remain unverified.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile render.yaml CLAUDE.md
git commit -m "build: deploy the bills service as a second Render service"
```

## Definition of Done

- [ ] `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ tests/common/ -q` green, 1 xfailed.
- [ ] `tests/chat/` failure count unchanged at 21.
- [ ] No test in the repo runs behind a password gate — the unset-password path installs no middleware.
- [ ] The report states plainly that the Docker build and `002_bills_audit.sql` were not executed.

## First-deploy checklist (for the human, not the implementer)

1. Run `db/migrations/002_bills_audit.sql` against the `BILLS_WRITE_DATABASE_URL` database.
2. Set the four env vars on `erp-bills` in the Render dashboard.
3. After the first real commit, confirm a row landed in `ERPAgent_BillAudit`.
4. Confirm `/healthz` is reachable and every other path returns 401 without credentials.
