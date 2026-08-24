# Bills Service Deployment — Design

**Date:** 2026-08-18
**Status:** Approved
**Related:** [2026-08-17-at-qr-extraction-design.md](2026-08-17-at-qr-extraction-design.md)

## Goal

Run the bill ingestion service on Render alongside the existing chat service, with an
authentication gate in front of it and an audit trail that survives a restart.

The service is not currently deployed at all: the Dockerfile CMD runs `logic.chat.app` and
`render.yaml` defines only `erp-chat`. Standing it up is not just a config change — two
properties that are acceptable on a laptop are not acceptable on the public internet.

## The two problems deployment exposes

**No authentication.** `logic/chat/app.py` gates every path except `/healthz` behind
`APP_PASSWORD`. `logic/bills/app.py` has no equivalent: its only notion of identity is a
`bills_operator` cookie, and `POST /bills/operator` sets it to any name the caller supplies.
Deployed as-is, anyone who finds the URL can upload an invoice and commit a write to the
ForumSI database. This is the more serious of the two, because the bills service is the one
that writes.

**An audit trail on ephemeral disk.** `BILLS_WRITE_LOG_PATH` defaults to
`logs/bills_writes.jsonl`, and Render's free tier discards the filesystem on every restart and
redeploy. CLAUDE.md states the audit trail is non-negotiable and that every mutation must be
traceable to a timestamp, a user, and the rule that authorised it. A log that evaporates does
not satisfy that.

## Decisions

**One Dockerfile, two Render services**, differing only by `dockerCommand`. The alternative —
a second Dockerfile — duplicates the Microsoft ODBC driver setup, including the SHA-1
signing-key workaround and the explicit `libgssapi-krb5-2`, and that is exactly the kind of
duplication that drifts when someone fixes one copy. The cost is that the chat image also
carries ~150MB of OCR binaries it never invokes.

**Separate passwords, shared implementation.** Bills gets `BILLS_APP_PASSWORD`, not a share of
`APP_PASSWORD`, so leaking the read-only chat service's credential does not hand over the
service that writes to the database.

**The audit row is written inside the document's own transaction.** Either both land or
neither. A best-effort audit is precisely the thing that turns out not to be there when
someone finally goes looking.

## Architecture

### logic/common/password_gate.py (new)

    install_password_gate(app, password, *, realm,
                          exempt=frozenset({"/healthz"})) -> None

Registers the HTTP middleware `logic/chat/app.py` has today: when a password is configured and
the path is not exempt, require HTTP Basic, compare **only the password part** using
`secrets.compare_digest` (the username is ignored, as now), and otherwise return 401 with a
`WWW-Authenticate` header.

**When the password is None the gate is not installed at all.** That keeps local development
and the existing test suite working untouched, and it is the property most likely to be broken
by a careless refactor.

`logic/chat/app.py` switches to calling it with `APP_PASSWORD` and realm "ERP Chat" — a
behaviour-preserving change, verified by chat's existing tests. `logic/bills/app.py` calls it
with `BILLS_APP_PASSWORD` and realm "Bill Ingestion".

### /healthz on the bills app

Returns `{"status": "ok"}`. Two constraints, both load-bearing:

- It must be registered **before** the `StaticFiles` mount at `/`, or the UI catch-all
  swallows it.
- It must be in the gate's exempt set, or Render's health check receives a 401 and the service
  never becomes live.

### Audit persistence

    service.commit()
       |
       +- executor.execute(plan, rule, operator=..., audit=...)
       |     +- one transaction:  supplier -> document -> lines -> AUDIT ROW
       |                          commit, or roll back all of it
       |
       +- on failure: audit.record_failure(...) opens its OWN session
                      (the write transaction has already rolled back)

**db/migrations/002_bills_audit.sql (new)** creates the audit table in the database reached by
`BILLS_WRITE_DATABASE_URL`. It must live there rather than anywhere tidier, because atomicity
requires it to share the document write's transaction. Columns: `Id` (identity PK), `Ts`,
`Operator`, `ProposalId`, `Status`, `DocumentChave`, `SupplierChave`, `RuleDoc`,
`RuleVersion`, and `Payload` — the full entry as JSON, so a future field costs no migration.
Indexed on `Ts` and `DocumentChave`. Guarded so re-running it is harmless.

**db/bills_audit.py (new)** holds `insert_audit(session, entry)`, which executes the
parameterised INSERT on a session it is handed. It knows nothing about bills business rules —
the entry arrives already built, matching the layering rule that the data layer trusts the
layer above to have validated.

**logic/bills/audit_writer.py (modified)** keeps building the entry exactly as it does now. It
gains two entry points:

- `insert(session, operator=, plan=, result=, status=)` — used by the executor inside the
  write transaction. This is the record of truth.
- `record_failure(operator=, plan=, result=, status=)` — opens its own session, because the
  write transaction has rolled back by the time a failure is known. Best-effort: if this insert
  also fails, which is likely when the DB is why the write failed, it must not mask the
  original error.

The existing JSONL file stays as a **mirror**, not the record of truth. It is written on
every record, success and failure alike, immediately after the database write is attempted, and
its writes remain best-effort with exceptions swallowed exactly as today. It is not a local-dev
substitute — `get_bills_write_session` raises without `BILLS_WRITE_DATABASE_URL`, so a commit
cannot happen at all without the write database. Its value is as an on-box diagnostic and as
the surviving copy when the audit INSERT itself fails.

**logic/bills/write_executor.py (modified)** — `execute` gains `operator` and `audit` keyword
arguments and inserts the audit row as the last statement inside its existing
`with self._factory() as session:` block. `logic/bills/service.py` passes them through and
keeps its own failure-path call.

### Dockerfile

Add `tesseract-ocr`, `tesseract-ocr-por` and `poppler-utils` to the existing apt layer.
`tesseract-ocr-por` is not optional: `ocr.pdf_to_text` calls Tesseract with `lang="por+eng"`
and fails outright without the Portuguese traineddata. CMD stays on the chat app so a bare
`docker run` behaves as it does today.

### render.yaml

A second `web` service, `erp-bills`, same `dockerfilePath`, with a `dockerCommand` running
`logic.bills.app`, `healthCheckPath: /healthz`, and four `sync: false` env vars:
`ANTHROPIC_API_KEY`, `DATABASE_URL` (read-only lookups), `BILLS_WRITE_DATABASE_URL` (the
writable ForumSI login), and `BILLS_APP_PASSWORD`. `BILLS_TABLE_PREFIX` keeps its
`ForumSI.dbo.` default rather than becoming another knob to get wrong.

## Testing

- `tests/common/test_password_gate.py` — an unset password installs no gate and every path
  passes; a missing or wrong credential gets 401 carrying `WWW-Authenticate`; the right
  password passes; an exempt path is reachable unauthenticated; the username is ignored.
- `tests/bills/test_app.py` — `/healthz` answers `{"status": "ok"}` without credentials, and
  answers even when `BILLS_APP_PASSWORD` is set.
- `tests/chat/` — existing tests must pass unchanged; that is the evidence the extraction was
  behaviour-preserving.
- `tests/bills/test_write_executor.py` — the audit row is inserted **on the same session** as
  the document, as the last statement before commit; a write that raises produces **no** audit
  row from the executor; `execute` still returns the same result shape.
- `tests/bills/test_audit_writer.py` — the entry keeps its current shape; `record_failure` uses
  its own session; a failing DB insert falls back to the file and does not raise.

## What cannot be verified here, and must be checked on first deploy

Stated plainly because it would otherwise read as tested:

- **No Docker locally**, so the image is never built here. That the apt layer resolves, that
  `import cv2` succeeds against `libglib2.0-0`, and that Tesseract finds `por` are all
  unverified.
- **No SQL Server locally**, so `002_bills_audit.sql` is never executed and the audit INSERT is
  exercised only against a fake session. The migration must be run by hand against the target
  database before the service is deployed, and the first real commit checked for an audit row.

## Out of scope

- Any change to how invoices are extracted, matched, staged or written.
- Per-operator accounts or roles; the shared password plus the operator-name cookie is the
  model, unchanged in kind.
- Migrating chat's existing JSONL audit to the database.
- Retention, rotation or archival of audit rows.
