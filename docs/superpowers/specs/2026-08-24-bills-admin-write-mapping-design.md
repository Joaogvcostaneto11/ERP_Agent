# Admin-Authored Write Mapping for Bills — Design

**Date:** 2026-08-24
**Status:** Approved (design); pending implementation plan
**Module:** `logic/bills` (write path)

## Problem

How an extracted bill becomes rows in the ERP database is fixed in
`business_rules/bills/purchase_invoice.yaml`. That document maps each extracted field to a
column — `bill.net_total` → `Doc001.Iliquido`, `line.description` → `LinDoc001.Descricao` — and
declares the `create_columns` whitelist bounding what a newly created supplier or article may
contain.

Changing any of it is a developer task: edit YAML, commit, deploy. An admin who knows that a
particular value belongs in a different column, or that a column the ERP expects is not being
populated at all, cannot express that. The knowledge that makes the write *correct for this
business* lives outside the system.

Parsing is not the problem being solved here. Extraction accuracy is adequate; the gap is
between a correctly-read invoice and the rows it should produce.

## Goal

Let an admin describe, in prose, how bill data should map onto database columns, and have that
become a durable, versioned, validated change to the write mapping — without a deploy, and
without prose or model output ever reaching the SQL.

The operator workflow — upload, review, correct, confirm — is unchanged.

## The constraint that shapes everything

`write_executor.py:46` builds its statement by interpolating column names into SQL:

```python
session.execute(text(f"INSERT INTO {self._p}{table} ({cols}) VALUES ({binds})"), row)
```

Values are bound parameters. **Identifiers are not.** `_check_columns` is what keeps this safe,
and the set it checks against comes from the rule document — `rule.header.fields`,
`rule.lines.fields`, and the two `create_columns` lists.

Today that boundary rests on "a developer wrote this YAML and git reviewed it." Making the
document admin-editable moves it to "whatever the admin typed." The design must therefore
replace the guarantee, not relocate it. It does so by validating every proposed identifier
against `INFORMATION_SCHEMA.COLUMNS` for the actual target table, which is a stronger check than
the git review it replaces.

## Decisions (from brainstorming)

| Decision | Choice | Rationale |
|---|---|---|
| Authoring input | Prose, drafted into structure by Claude | What the admin asked for; matches chat's agent-drafted / human-approved loop. |
| What executes | The validated `PurchaseInvoiceRule` only | Model output is a *candidate patch*, never a write instruction. |
| Identifier safety | Live `INFORMATION_SCHEMA` check + identifier regex | Replaces the git-review guarantee with a verified one. |
| Approval | Admin reviews a concrete before/after diff | Prose is ambiguous; a diff is not. |
| Versioning | Bump `version`, keep prior YAML on disk | `WritePlan.rule_version` already records which version authorized each write. |
| Reversibility | Revert to any prior version | A bad mapping writes wrong data until corrected. |
| Conditional logic | Out of scope for v1 | Needs executor code, not just YAML. See below. |
| Trust model | Shared `BILLS_ADMIN_TOKEN` | The system has no user accounts. |

## Architecture

```
ui/bills/  ── Admin panel (token-gated; operators never see it)
   │  prose: "the supplier's own article code belongs in LinDoc001.CodigoForn"
   ▼
logic/bills/app.py
   ├── GET  /admin/rules/enabled          # feature on?
   ├── GET  /admin/rules/current  (gated) # rule + version + schema + history
   ├── POST /admin/rules/draft    (gated) # prose → validated proposal + diff
   ├── POST /admin/rules/apply    (gated) # approve → new version, audit, reload
   └── POST /admin/rules/revert/{v}(gated)
   │
   ├── SchemaProbe    (logic/bills/rules/schema_probe.py)   ← INFORMATION_SCHEMA
   ├── RuleProposer   (logic/bills/rules/proposal.py)       ← Claude drafts, we validate
   ├── RuleStore      (logic/bills/rules/store.py)          ← versioned YAML on disk
   └── AuditLog → logs/bills_writes.jsonl  (kind="rule_change")
```

The flow is deliberately three-staged: **draft** produces a candidate, **validate** decides
whether it is representable, **apply** persists it. Only the third writes anything, and it
operates on structure that has already passed every check.

### `logic/bills/rules/schema_probe.py` (new)

Queries `INFORMATION_SCHEMA.COLUMNS` for the tables the rule names — `Doc001`, `LinDoc001`,
`Entidades`, `Artigos` — returning `{table: {column_name: ColumnInfo}}` with data type and
nullability. Reads go through the existing read session, the same path the matcher already uses.

Cached for the process, refreshed on demand. This module is the sole authority on what
identifiers exist; nothing else may vouch for a column name.

### `logic/bills/rules/proposal.py` (new)

`RuleChangeProposal` is a pydantic model describing a patch: fields to add, retarget, or remove
across `header.fields`, `lines.fields`, and the two `create_columns` lists.

> **Amended 2026-08-24 after the final review — the two `create_columns` lists are NOT
> admin-editable.** `validate()` rejects every change whose section is `supplier_create` or
> `article_create`, and the drafting prompt does not offer them.
>
> The reason is that `create_columns` is only a *whitelist*, not a source. `logic/bills/matching.py`
> hardcodes the new-entity payload (`Nome`, `NCont` for a supplier; `Nome` for an article) and
> `write_executor._check_columns` merely checks that payload against the list. So *adding* a
> create column changed nothing that is ever written, and *removing* one made `_check_columns`
> raise `ValueError` — which `/bills/commit` does not catch, since it catches `RuntimeError`.
> Every bill with an unmatched supplier would have returned HTTP 500 until an admin reverted.
> An admin working entirely inside the panel could break ingestion with an opaque error.
>
> Making them genuinely editable requires deriving the payload from `create_columns` in
> `matching.py`, which needs a source mapping per create column. That is a design change, not a
> fix, and is deliberately left for a follow-up. The protected-column logic underneath remains
> in place as defence in depth.

- `draft(prose, current_rule, schema, sources) -> RuleChangeProposal` — Claude is asked for
  **structured JSON matching this model**, with the current mapping, the real column list, and
  the available sources supplied as context. It is not asked for SQL, YAML, or prose.
- `validate(proposal, current_rule, schema) -> list[Violation]` — four independent checks:
  1. every target column exists in `INFORMATION_SCHEMA` for that specific table, matched
     case-insensitively but **persisted using the schema's exact spelling**;
  2. every identifier additionally matches `^[A-Za-z_][A-Za-z0-9_]*$` — defence in depth, so a
     hostile or malformed schema row still cannot reach the INSERT;
  3. every `source` names a real extracted field — `bill.<f>` from `Bill`, `line.<f>` from
     `BillLine`, or the two `.match` sentinels;
  4. no protected column is targeted (below).
- `apply(proposal, current_rule) -> PurchaseInvoiceRule` — a pure merge that bumps `version`.
  Re-validated through `PurchaseInvoiceRule.model_validate`, whose `extra="forbid"` catches
  anything structural the checks above missed.

**Protected columns.** The header `primary_key`, every key in `audit_columns`, and every key in
`draft_defaults` are rejected as admin targets. The executor applies these last precisely so a
caller cannot override them; letting an admin remap them through the front door would undo that.

A proposal that fails validation is returned to the admin with its violations and is not
persistable. There is no override.

### `logic/bills/rules/store.py` (new)

Persists the approved rule to `business_rules/bills/purchase_invoice.yaml`, writing via a
temporary file and atomic replace so an interrupted save cannot leave a half-written document
that fails to load at next boot.

Before overwriting, the current file is copied to
`business_rules/bills/history/purchase_invoice.v{N}.yaml`. Revert re-applies a historical file as
a new version — history is append-only, so reverting from v5 to v3 produces v6 with v3's content
and leaves the record of v4 and v5 intact.

`RuleLoader` parses the YAML once in `__init__`, and `get_service()` memoises the service built
from it, so applying a change must reset that singleton. This mirrors `reset_service()` in
`logic/chat/app.py`.

**Concurrent edits.** A proposal is drafted against a specific version, and the admin may sit on
the diff for some time before approving. If another admin applies a change meanwhile, blindly
merging the stale proposal would silently drop their work — or worse, reinstate a mapping they
had just removed. `POST /admin/rules/apply` therefore carries the `base_version` the proposal was
drafted against and is rejected with 409 if the current version has moved. The admin re-drafts
against the new baseline. This is optimistic concurrency, and it is cheap here because the
version number already exists.

### Admin gate

`BILLS_ADMIN_TOKEN` supplied as `X-Admin-Token`, compared with `secrets.compare_digest`. Unset
means the feature is off and every `/admin/rules*` route returns 404; a wrong token returns 403.
The shape copies `_require_feedback` in `logic/chat/app.py`.

This is a third secret, deliberately distinct from `BILLS_APP_PASSWORD` (may you use the service)
and `APP_PASSWORD` (the chat service), following the separation already argued in CLAUDE.md. An
admin holds two secrets; an operator holds one.

### Audit

Applying or reverting appends a `kind="rule_change"` row to the bills JSONL: action, from and to
version, the admin's prose, the structured diff, and the timestamp.

Not routed through `BillAuditWriter` — that class is `WritePlan`-shaped and exists to put its row
inside the document transaction. A rule change has no transaction to join.

Document-level traceability needs no new work: `WritePlan` already carries `rule_doc` and
`rule_version`, so every committed bill already records which mapping version authorized it. The
`rule_change` rows make that number resolvable to a diff and an author.

### UI

`ui/bills/` gains an admin panel, hidden unless `GET /admin/rules/enabled` is true **and** a token
is in `localStorage` — the pattern `ui/chat/app.js` already uses for Teach/Fix. The panel shows
the current mapping and version, a prose box that produces a proposal, the resulting before/after
diff or the list of violations, an Apply control, and the version history with revert.

Upload, review, and confirm are untouched.

## Error handling

| Case | Behavior |
|---|---|
| `BILLS_ADMIN_TOKEN` unset | All `/admin/rules*` routes 404. |
| Wrong or missing token | 403. |
| Claude returns unparseable or non-conforming JSON | 422 with the raw text; nothing persisted. |
| Proposal targets an unknown column | 422 listing each violation and the valid columns for that table. |
| Proposal targets a protected column | 422 naming the column and why it is protected. |
| Proposal names an unknown source | 422 listing the valid sources. |
| Merged rule fails `PurchaseInvoiceRule` validation | 422; the current YAML is untouched. |
| Schema probe cannot reach the database | 503. Validation must never be skipped, so drafting is refused rather than degraded. |
| Apply whose `base_version` is no longer current | 409; another admin changed the mapping first. Re-draft. |
| Revert to a version with no history file | 404. |
| Save interrupted | Atomic replace; the previous document remains loadable. |

## Testing

Schema probe (`tests/bills/test_schema_probe.py`), against a fake reader: shape of the returned
map; unknown table yields empty; results cached and refreshable.

Validation (`tests/bills/test_rule_proposal.py`) — the security core, tested adversarially:

- a column absent from the target table is rejected
- a column that exists **but on a different table** is rejected
- an injection-shaped identifier (`Descricao); DROP TABLE`) is rejected by the regex even if the
  schema check is stubbed to pass
- an unknown `source` is rejected
- `primary_key`, `audit_columns`, and `draft_defaults` keys are each rejected as targets
- a valid proposal merges, bumps `version`, and survives `PurchaseInvoiceRule.model_validate`
- the persisted column uses the schema's exact spelling when the admin's case differs

Store (`tests/bills/test_rule_store.py`): apply writes history then the new document; an
interrupted write leaves the prior document intact; revert produces a new version carrying the
old content; history is not rewritten by a revert.

Endpoints (`tests/bills/test_admin_rules.py`): 404 disabled, 403 bad token, draft → apply
round-trip, one `rule_change` audit row per apply, the service reload picking up the change, and
an apply carrying a stale `base_version` rejected with 409 without touching the document.

The existing `tests/bills` suite is the operator-path regression guard, and the existing
`write_executor` tests already cover `_check_columns` rejecting anything outside the whitelist —
that behavior must not change.

## Out of scope

- **Conditional mappings** ("when VAT rate is 6, write X"). The current model is
  `{column, source, required}`; conditionals need new executor logic per form, not just new YAML.
  Deferred until the concrete cases are known.
- **Editing the `create_columns` whitelists** — closed after the final review; see the amendment
  under `proposal.py` above. Needs `matching.py` to derive its new-entity payload from the list
  before it can be reopened.
- Computed or derived values, expressions, and arithmetic in mappings
- Documents other than `purchase_invoice` (DevCare's rules stay developer-owned)
- Editing `table`, `parent_fk`, or `tipo_doc` — structural identity, not mapping
- Automatic git commit of the changed YAML; as with chat's knowledge file, that stays manual
- Real user accounts and roles
