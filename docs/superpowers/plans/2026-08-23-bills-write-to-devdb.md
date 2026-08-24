# Bills Write Target — DevDB Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bill ingestion write to DevDB instead of the ForumSI mirror, by having the write target follow whichever database `BILLS_WRITE_DATABASE_URL` connects to.

**Architecture:** Two hardcoded `"ForumSI.dbo."` defaults and one `USE ForumSI` in a migration currently pin writes to the mirror regardless of the connection. Changing the default table prefix to `"dbo."` makes the connection's own database the single lever, so the application and the migration can no longer disagree about where rows go.

**Tech Stack:** Python 3.12, SQLAlchemy Core, pyodbc, SQL Server, pytest.

## Why this shape

`BILLS_WRITE_DATABASE_URL` already names a database — currently `DevDB`. Keeping a second, independent statement of the target in `BILLS_TABLE_PREFIX` means two levers that can drift apart, and they already did: the previous migration created the audit table in the connection's database while the application inserted into `ForumSI.dbo.`, which would have failed every commit on a missing object.

`"dbo."` removes the second lever. To point the service at ForumSI later, change the URL — nothing else. `BILLS_TABLE_PREFIX` stays available as an override for anyone who genuinely needs cross-database writes.

**Verified against the live server (2026-08-23):** `DevDB.dbo` already contains `Doc001`, `LinDoc001`, `Entidades`, `Artigos` and `TiposDoc`. Only `ERPAgent_BillAudit` is missing there — Task 3 creates it.

## Global Constraints

- The default write target is the connection's own database. Code must contain no hardcoded database name.
- `BILLS_TABLE_PREFIX` keeps working as an override; only its **default** changes, from `"ForumSI.dbo."` to `"dbo."`.
- `db/migrations/002_bills_audit.sql` must not name a database either — it runs in whatever database the connection is pointed at.
- The audit row is inserted inside the document's transaction, so the audit table must live in the same database as `Doc001`. With the prefix following the connection, that is automatic rather than a thing to remember.
- Do NOT drop `ForumSI.dbo.ERPAgent_BillAudit`. The human ruled: leave it in place.
- No new package dependencies. Offline tests stay offline and deterministic.
- Interpreter: `C:/Users/joaog/erp_venv/Scripts/python.exe` — the repo's `.venv` is corrupted by OneDrive sync.
- Baseline: `tests/bills/` + `tests/common/` is **187 passed, 1 xfailed**. `tests/chat/` has **21 pre-existing failures** unrelated to this work — do not fix them, do not add to them.

## File Structure

| File | Responsibility |
|---|---|
| `logic/bills/write_executor.py:23` (modify) | `table_prefix` default → `"dbo."` |
| `logic/bills/app.py:31` (modify) | `_TABLE_PREFIX` env default → `"dbo."`; stale ForumSI comment |
| `db/migrations/002_bills_audit.sql` (modify) | Drop `USE ForumSI`; run in the connection's database |
| `tests/bills/test_write_executor.py` (modify) | Pin the new default |
| `tests/bills/test_bills_audit_sql.py` (modify) | Adds a default-prefix guard; the existing explicit-prefix test stays, since honouring an override is still correct |
| `tests/bills/test_app.py:94` (modify) | Stale docstring wording |
| `CLAUDE.md`, `render.yaml` (modify) | Stale ForumSI wording |

---

### Task 1: The write target follows the connection

**Files:**
- Modify: `logic/bills/write_executor.py:23`, `logic/bills/app.py:31` and its comment at line 35
- Test: `tests/bills/test_write_executor.py`, `tests/bills/test_bills_audit_sql.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `BillWriteExecutor(session_factory, *, table_prefix="dbo.", ...)`. No signature change — only the default value.

- [ ] **Step 1: Write the failing test**

Append to `tests/bills/test_write_executor.py`:

```python
def test_default_table_prefix_follows_the_connection_database():
    """No hardcoded database name: the target is whatever
    BILLS_WRITE_DATABASE_URL connects to.

    Two independent statements of the target drift apart — that is exactly how
    the audit table once ended up in a different database from the documents,
    which would have failed every commit on a missing object.
    """
    ex = BillWriteExecutor(lambda: None)
    assert ex._p == "dbo."
    assert "ForumSI" not in ex._p
```

Append to `tests/bills/test_bills_audit_sql.py`:

```python
def test_insert_defaults_to_the_connection_database():
    s = FakeSession()
    insert_audit(s, ENTRY)
    sql, _ = s.calls[0]
    assert f"INSERT INTO {TABLE}" in sql
    assert "ForumSI" not in sql
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_write_executor.py::test_default_table_prefix_follows_the_connection_database tests/bills/test_bills_audit_sql.py::test_insert_defaults_to_the_connection_database -v`

Expected: the executor test FAILS with `AssertionError` comparing `'ForumSI.dbo.'` to `'dbo.'`. The audit test PASSES already — `insert_audit`'s own default prefix is `""`, so it is a regression guard rather than a driver.

- [ ] **Step 3: Write minimal implementation**

In `logic/bills/write_executor.py:23`, change the default:

```python
                 table_prefix: str = "dbo.",
```

In `logic/bills/app.py:31`:

```python
# Writes land in whatever database BILLS_WRITE_DATABASE_URL points at (DevDB).
# Deliberately not a second, independent statement of the target: when the
# prefix named a database of its own, it drifted from the connection and the
# audit table was created somewhere the inserts never looked.
_TABLE_PREFIX = os.environ.get("BILLS_TABLE_PREFIX", "dbo.")
```

Also fix the now-stale comment at `logic/bills/app.py:35`, replacing "the ForumSI database" with "the ERP database".

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ tests/common/ -q`
Expected: PASS, 1 xfailed. Existing tests already pass an explicit `table_prefix`, so none should break — if one does, read it before changing it.

- [ ] **Step 5: Commit**

```bash
git add logic/bills/write_executor.py logic/bills/app.py tests/bills/test_write_executor.py tests/bills/test_bills_audit_sql.py
git commit -m "fix(bills): write to the connection's database, not a hardcoded ForumSI"
```

---

### Task 2: The migration stops naming a database

**Files:**
- Modify: `db/migrations/002_bills_audit.sql`

**Interfaces:**
- Consumes: Task 1's decision that the prefix follows the connection.
- Produces: a migration that creates `dbo.ERPAgent_BillAudit` in whatever database it is run against.

- [ ] **Step 1: Rewrite the header comment and drop the USE**

Replace the file's leading comment block and remove both the `USE ForumSI;` line and the `GO` that follows it, so the script is a single batch. The comment must explain the invariant rather than the history:

```sql
-- Audit trail for bill ingestion writes.
--
-- WHERE THIS LIVES, AND WHY IT MATTERS
-- Run this against the database BILLS_WRITE_DATABASE_URL points at — the same
-- one the application writes documents to. It deliberately does NOT name a
-- database: the audit row is inserted inside the document's own transaction, so
-- it has to sit beside Doc001, and the only way to guarantee that is to let both
-- follow the same connection. When the two named their targets separately they
-- drifted, and every audit INSERT would have failed on a missing object.
--
-- Payload holds the whole audit entry as JSON, so adding a field later needs no
-- migration; the promoted columns exist only to make the common queries cheap.
--
-- Ts is NVARCHAR rather than DATETIME2 on purpose: AuditLog.now_iso() already
-- produces a sortable ISO-8601 UTC string, and storing it verbatim keeps this
-- column identical to the JSONL mirror's value with no driver-dependent
-- conversion in between.
--
-- Re-running this script is harmless.
```

Keep the `IF OBJECT_ID('dbo.ERPAgent_BillAudit', 'U') IS NULL` guard, the `CREATE TABLE`, and both `CREATE INDEX` statements exactly as they are.

- [ ] **Step 2: Verify the script no longer names a database**

Run:

```bash
grep -n "ForumSI\|USE " db/migrations/002_bills_audit.sql
```

Expected: no matches. If `grep` exits non-zero with no output, that is the pass condition.

- [ ] **Step 3: Commit**

```bash
git add db/migrations/002_bills_audit.sql
git commit -m "fix(db): run the audit migration in the connection's database"
```

---

### Task 3: Create the audit table in DevDB and prove the write path works

This task touches a live database. It is additive — one `CREATE TABLE` guarded by an existence check, plus a probe that is rolled back.

**Files:**
- No repository files. This is execution and verification.

**Interfaces:**
- Consumes: the migration from Task 2, `insert_audit` from `db/bills_audit.py`.
- Produces: `DevDB.dbo.ERPAgent_BillAudit`.

- [ ] **Step 1: Confirm the target before touching anything**

```python
import os, pathlib
for line in pathlib.Path(".env").read_text(encoding="utf-8").splitlines():
    if line.startswith("BILLS_WRITE_DATABASE_URL="):
        os.environ["BILLS_WRITE_DATABASE_URL"] = line.split("=", 1)[1].strip()

from sqlalchemy import create_engine, text
eng = create_engine(os.environ["BILLS_WRITE_DATABASE_URL"], pool_pre_ping=True)
with eng.connect() as c:
    print("database:", c.execute(text("SELECT DB_NAME()")).scalar())
    print("Doc001 here:", c.execute(text("SELECT OBJECT_ID('dbo.Doc001')")).scalar() is not None)
```

Expected: `database: DevDB` and `Doc001 here: True`. **If the database is not DevDB, stop and report** — do not create tables somewhere unexpected.

- [ ] **Step 2: Run the migration**

Execute the script from Task 2 against that connection with `isolation_level="AUTOCOMMIT"`. It is now a single batch, so no `GO` splitting is needed.

- [ ] **Step 3: Verify the table, its columns and its indexes**

```python
with eng.connect() as c:
    print("exists:", c.execute(text("SELECT OBJECT_ID('DevDB.dbo.ERPAgent_BillAudit')")).scalar() is not None)
    print("columns:", [r[0] for r in c.execute(text(
        "SELECT COLUMN_NAME FROM DevDB.INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = 'ERPAgent_BillAudit' ORDER BY ORDINAL_POSITION"))])
    print("indexes:", [r[0] for r in c.execute(text(
        "SELECT name FROM DevDB.sys.indexes WHERE object_id = "
        "OBJECT_ID('DevDB.dbo.ERPAgent_BillAudit') AND name IS NOT NULL"))])
```

Expected columns, in order: `Id, Ts, Operator, ProposalId, Status, DocumentChave, SupplierChave, RuleDoc, RuleVersion, Payload`. Expected indexes: a primary key plus `IX_ERPAgent_BillAudit_Ts` and `IX_ERPAgent_BillAudit_Doc`.

- [ ] **Step 4: Exercise the real INSERT and roll it back**

This is the step that proves the migration and the code agree — a table existing is not the same as the application's statement working against it.

```python
from db.bills_audit import insert_audit
entry = {"ts": "2026-08-23T00:00:00.000Z", "kind": "bill_ingest", "operator": "__probe__",
         "proposal_id": "probe", "document_chave": None, "supplier_chave": None,
         "line_chaves": [], "created_supplier": False, "created_articles": [],
         "rule_doc": "purchase_invoice", "rule_version": 1, "status": "ok"}
with eng.connect() as c:
    t = c.begin()
    insert_audit(c, entry, table_prefix="dbo.")     # the new default
    print("visible in transaction:",
          c.execute(text("SELECT COUNT(*) FROM dbo.ERPAgent_BillAudit "
                         "WHERE Operator = '__probe__'")).scalar())
    t.rollback()
with eng.connect() as c:
    print("rows after rollback:",
          c.execute(text("SELECT COUNT(*) FROM DevDB.dbo.ERPAgent_BillAudit")).scalar())
```

Expected: `visible in transaction: 1`, then `rows after rollback: 0`. A non-zero count after the rollback means the probe leaked — report it rather than deleting rows to tidy up.

- [ ] **Step 5: Report, do not commit**

Nothing here changes the repository. Report the actual output of every step above, including the database name from Step 1.

---

### Task 4: Retire the stale ForumSI wording

Documentation and comments still describe the write target as the ForumSI mirror, which is now wrong and would mislead the next person.

**Files:**
- Modify: `CLAUDE.md:120`, `render.yaml`, `tests/bills/test_app.py:94`

**Interfaces:**
- Consumes: nothing. Text only.

- [ ] **Step 1: Update the three references**

In `CLAUDE.md:120`, change "a writable login scoped to the ForumSI mirror" to "a writable login for the ERP database (currently DevDB); writes land in whatever database that URL names".

In `render.yaml`, change the comment `# writable ForumSI login` to `# writable ERP login (DevDB)`.

In `tests/bills/test_app.py:94`, change the docstring "The service that writes to ForumSI must not be open to the internet." to "The service that writes to the ERP database must not be open to the internet."

Leave every other `ForumSI` reference alone. `docs/db_schema.md`, `business_rules/query_knowledge.md` and `scripts/regen_schema_inventories.py` describe the server's databases as they actually are — ForumSI still exists and is still a mirror. Only statements about **where bills are written** are wrong.

- [ ] **Step 2: Confirm the remaining references are all legitimate**

```bash
grep -rn "ForumSI" --include=*.py --include=*.yaml --include=*.md . | grep -v "^./docs/superpowers" | grep -v "^./.superpowers"
```

Expected: matches only in `docs/db_schema.md`, `business_rules/query_knowledge.md` and `scripts/regen_schema_inventories.py` — all of which describe the server's databases as they actually are. `db/migrations/002_bills_audit.sql` must NOT appear: Task 2 removes its last ForumSI mention. No remaining match may describe the bills write target.

- [ ] **Step 3: Run the suite and commit**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ tests/common/ -q`
Expected: PASS, 1 xfailed.

```bash
git add CLAUDE.md render.yaml tests/bills/test_app.py
git commit -m "docs(bills): the write target is the ERP database, not the ForumSI mirror"
```

## Definition of Done

- [ ] `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ tests/common/ -q` green, 1 xfailed.
- [ ] `tests/chat/` failure count unchanged at 21.
- [ ] No hardcoded database name anywhere in `logic/` or `db/migrations/002_bills_audit.sql`.
- [ ] `DevDB.dbo.ERPAgent_BillAudit` exists, and the real `insert_audit` statement was executed against it and rolled back cleanly.
- [ ] `ForumSI.dbo.ERPAgent_BillAudit` is still present and untouched — the human ruled to leave it.
