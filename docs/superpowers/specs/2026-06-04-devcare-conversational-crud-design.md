# DevCare Conversational CRUD — Design Spec

**Date:** 2026-06-04
**Branch:** `devcare_crud` (off `scrm_module`)
**Status:** Approved design, pending implementation plan

## 1. Goal

Let an operator perform safe Create / Update / Delete operations on the **DevCare**
database through conversation: the operator describes what they want, the system
asks the questions needed to fill in a curated entity, shows an exact preview, and
only writes after the operator explicitly confirms.

This is the first **write** capability in the system. The existing chat
(`logic/chat/`) stays strictly read-only and is not modified by this work.

## 2. Scope

### In scope (v1)
- A new isolated write module, `logic/devcare/`, with its own AI orchestration loop.
- A curated, versioned entity registry in `business_rules/devcare/`.
- Two starting entities: **Patients (`Entidades`)** and **Specialties (`Especialidades`)**.
- Create, Update, and soft-Delete for those entities.
- Explicit preview + confirm gate on **every** write.
- Lightweight operator identity captured at session start.
- App-side structured audit log (one record per committed write).
- A new UI surface for the operations conversation + confirm card.

### Out of scope (v1)
- Generic any-table CRUD; only registered entities are writable.
- Mass / bulk updates and deletes (each update/delete targets a single resolved
  primary key).
- Password-based authentication or integration with DevCare `WebLogin`.
- Writing an audit table *into* DevCare (app-side log only for v1).
- CRUD on any database other than DevCare.

## 3. Key decisions (locked)

| Decision | Choice |
|---|---|
| Write surface | Few curated entities (registry-driven) |
| Starting entities | Patients (`Entidades`) + Specialties (`Especialidades`) |
| Confirm gate | Explicit preview + confirm for **every** write; model cannot self-commit |
| Identity | Lightweight operator name/login at session start, recorded per write |
| Delete semantics | Soft-delete via status/`Hist` flag where supported; hard delete opt-in per entity |
| Audit (v1) | App-side structured log (extends existing `AuditLog`) |
| Architecture | Separate module reusing chat infra (read-only chat untouched) |

## 4. Architecture

```
ui/devcare/            conversation pane + pending-change confirm card
   │  SSE stream  +  POST /devcare/commit/{change_id}
logic/devcare/         orchestrator (AI loop), validator, write executor, rules
   │  reads: existing read-only login (DATABASE_URL)
   │  writes: NEW writable login (DEVCARE_WRITE_DATABASE_URL), DevCare only
business_rules/devcare/<entity>.yaml   ← source of truth for writable entities
```

**Request flow**

1. Operator describes intent in natural language.
2. Orchestrator identifies entity + operation, asks for missing required fields
   (defined by the entity YAML).
3. When complete, the model calls `propose_change`; the validator checks the
   change and **stages** it (no write); a preview block is rendered.
4. Operator clicks **Confirm** → `POST /devcare/commit/{change_id}`.
5. Server executes the staged change via the write executor in one transaction,
   writes an audit record, returns the result.
6. Operator may continue with another operation in the same conversation.

## 5. Enterprise document schema (`business_rules/devcare/<entity>.yaml`)

Each file defines one writable entity. Example shape:

```yaml
entity: patient
version: 1
table: Entidades
primary_key: Chave
operations: [create, update, delete]

soft_delete:
  column: Estado          # or Hist, per table
  active_value: 0
  deleted_value: 9

fields:
  name:
    column: Nome
    type: string
    required: true
    label: Full name
    validation: { max_length: 100 }
  tax_id:
    column: NIF
    type: string
    required: false
    validation: { regex: "^[0-9]{9}$" }
  specialty:
    column: Especialidade
    type: int
    required: false

references:                # logical FK checks (no real FKs in DB)
  specialty: { table: Especialidades, column: Chave }

uniqueness:
  - [tax_id]               # NIF must be unique among active rows
```

Rules:
- Only columns listed under `fields` are ever writable.
- `version` is bumped on breaking changes; the applied version is recorded in audit.
- A table absent from the registry can never be written.

## 6. Components (each independently testable)

### RuleLoader
Loads and validates the entity YAMLs into Pydantic models. Mirrors the existing
payroll rules loader pattern. Fails loudly on malformed/incomplete documents.
- **Depends on:** YAML files, Pydantic.
- **Used by:** ChangeValidator, DevCareService.

### ChangeValidator
Given `(entity, operation, fields, target_pk?)`, returns either a normalized,
ready-to-execute change or a list of violations. Checks:
- required fields present; types coercible; enum/range/regex constraints;
- `uniqueness` (read query against active rows);
- `references` existence (read query — substitutes for missing FKs);
- for update/delete: the target primary key resolves to exactly one row.

Records which rule document + version authorized the change.
- **Depends on:** RuleLoader, a read-only query function.
- **Used by:** DevCareService (via `propose_change`), commit endpoint (re-validates).

### WriteExecutor
Builds and runs the actual mutation. The write-side mirror of `SqlExecutor`.
- Identifiers (table, columns) come **only** from the registry — never from model
  output. Values are always bound parameters → no injection, no arbitrary tables.
- Executes inside a single transaction; rolls back on any error.
- Supports INSERT, UPDATE (single PK), and soft-delete (UPDATE of the status
  column) / opt-in hard delete.
- **Depends on:** writable engine (`DEVCARE_WRITE_DATABASE_URL`), the normalized
  change from ChangeValidator.

### DevCareService (AI orchestrator)
Streaming loop modeled on `ChatService`, with tools:
- `lookup(sql)` — read-only SELECT (reuses `SqlExecutor`) to resolve references and
  find rows to edit.
- `propose_change(entity, operation, fields, target)` — runs ChangeValidator; on
  success stages a pending change and emits a **preview block**; on failure emits
  the violations. **Never writes.**
- There is **no** model-callable commit tool. Commit is user-driven only.
- **Depends on:** Anthropic client, RuleLoader, ChangeValidator, a pending-change
  store, AuditWriter.

### Commit endpoint
`POST /devcare/commit/{change_id}`: re-validates the staged change, executes it via
WriteExecutor, writes the audit record, returns success/error. Idempotent on an
already-committed id.

### AuditWriter
Extends the existing `AuditLog`. One record per commit:
`{ ts, operator, entity, operation, table, primary_key, before, after, rule_doc,
rule_version, status }`. `before` is captured for update/delete.

## 7. Safety model (defense in depth)

1. Separate writable login; the read-only chat login is unchanged and the chat's
   SELECT-only enforcement stays intact.
2. WriteExecutor only touches whitelisted tables/columns from the registry.
3. Every write runs inside an explicit transaction; rollback on any error.
4. Two-phase: `propose` (validate, no write) → human **Confirm** → `commit`. The
   model cannot self-commit.
5. Updates/deletes require a single resolved primary key — no mass operations.
6. Soft-delete by default.
7. Recommended (operator-provided): the writable login is permissioned at the DB
   level to only the curated tables, as a final backstop.

## 8. Identity

A simple prompt at session start captures the operator's name (and optional login
string). It is stored in the session and:
- attached to every audit record, and
- provided to the orchestrator as context (so it can address the operator and
  record who is acting).

No password infrastructure in v1.

## 9. UI

A new surface that reuses the SSE channel and block renderers, adding a
`pending_change` block kind and a confirm action.

```
┌─ DevCare Operations ────────────────────────────┐
│ you: register a new patient, João Silva…         │
│ ai : I need a few details — date of birth? NIF?  │
│ …                                                │
│ ┌ Pending change — CREATE Patient ────────────┐  │
│ │ Nome        João Silva                       │  │
│ │ NIF         123456789                        │  │
│ │ Especial.   Cardiology (#7)                  │  │
│ │ SQL: INSERT INTO Entidades (...) VALUES (?)  │  │
│ │             [ Cancel ]   [ Confirm write ]   │  │
│ └──────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────┘
```

- **Confirm** posts to the commit endpoint; on success the card collapses to a
  committed state and a success block appears.
- **Cancel** discards the staged change.

## 10. Error handling

| Situation | Behavior |
|---|---|
| Missing/invalid fields | Text block lists violations; model asks operator to fix, then re-proposes. |
| Reference / uniqueness failure | Surfaced at `propose` time, before any write. |
| DB error at commit | Transaction rolls back; error block shown; nothing persisted. |
| Confirm on a stale/expired change | Re-validation fails; operator asked to re-propose. |

## 11. Testing

- **Unit**
  - RuleLoader: valid load; rejects malformed/incomplete YAML.
  - ChangeValidator: each rule type (required, type, enum/range/regex, uniqueness,
    reference, single-PK resolution) with valid and invalid inputs; asserts which
    rule/doc was applied.
  - WriteExecutor: correct parameterized SQL for insert/update/soft-delete; table
    whitelist enforced; rollback on error — using a fake/in-memory session.
- **Integration**
  - Full `propose → confirm → commit` with a fake Anthropic client; asserts audit
    record contents and that **nothing commits without Confirm**.
  - DB-touching tests run inside a transaction that is rolled back afterward.
- Test layout mirrors payroll (`tests/devcare/...`).

## 12. Prerequisites / configuration

- `DEVCARE_WRITE_DATABASE_URL` — writable login scoped to DevCare (ideally
  permissioned to only the curated tables). Read-only `DATABASE_URL` stays for reads.
- No new Python dependencies (sqlalchemy, pydantic, pyyaml, anthropic already present).

## 13. Open items to resolve during planning

- Exact field subsets and the precise soft-delete column (`Estado` vs `Hist`) for
  `Entidades` and `Especialidades` — verify against live schema.
- Whether the operator-provided writable login already exists, or needs creating.
- Conversation persistence: reuse `HistoryStore`, or a lighter pending-change store.
