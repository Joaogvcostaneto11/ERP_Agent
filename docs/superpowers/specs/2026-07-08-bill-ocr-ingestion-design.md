# Bill OCR Ingestion — Design

**Date:** 2026-07-08
**Status:** Approved (design); implementation plan pending
**Branch context:** `scrm_module`

## Summary

A standalone interface for ingesting supplier bills. A user uploads a bill PDF; the
system OCRs it, uses Claude to extract a structured bill, matches the supplier and
line-item products against the ERP, and proposes a draft purchase document. On
operator acceptance, the data is written atomically to the mirror database as a
**draft, uncertified** purchase document.

This is a new ERP domain (`bills`) and follows the project's core constraints: AI is
authoritative for business logic, all writes flow UI → logic → db, and every mutation
is audited. The bill→ERP mapping lives in an enterprise document, not in code.

## Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Bill target | Supplier invoice → purchase `Doc001` header + `LinDoc001` lines | Accounts-payable ingestion; richest, most useful representation |
| Extraction engine | Tesseract OCR → text → Claude structures to JSON | User preference; keeps PDFs local. Image-augmentation is a documented drop-in |
| Write target | ForumSI mirror DB, `Doc001` as draft (`Estado=0`), uncertified | Reversible while building; avoids fiscal certification machinery |
| Matching | Match-or-create supplier + articles, operator confirms new records | Most capable; confirmation gate keeps it safe |
| Interaction model | Standalone interface: upload → editable review form → Accept | Task is mostly review-and-correct of a document |
| Module shape | New `logic/bills/` + `ui/bills/`, reuse DevCare write/audit primitives | Matches established module boundaries |

## Architecture

```
Upload PDF ─► OCR (Tesseract) ─► Claude extract ─► Match ─► Propose ─► Review form ─► Accept ─► Write (txn) ─► Audit
             raw text            structured bill    suppliers/   draft Doc001   operator edits         Doc001+LinDoc001
                                 (Pydantic)         articles     proposal                              (+new Entidade/Artigos)
```

### Module layout

```
logic/bills/
  app.py            # FastAPI app (new port): /bills/upload, /bills/stage, /bills/commit
  extract/
    ocr.py          # Tesseract wrapper: PDF -> page-tagged text (image drop-in later)
    parser.py       # Claude: text -> structured Bill (Pydantic)
  matching.py       # supplier + article match-or-create proposals (read-only)
  models.py         # Bill, BillLine, MatchResult, BillProposal schemas
  service.py        # orchestration: upload -> extract -> match -> propose -> stage -> commit
  write_executor.py # atomic multi-table insert to ForumSI mirror
  pending.py        # server-side proposal store (mirrors DevCare PendingChangeStore)
  rules/loader.py   # loads business_rules/bills/
business_rules/bills/
  purchase_invoice.yaml   # Doc001/LinDoc001 field map, draft defaults, TipoDoc, matching config
ui/bills/           # upload + review-form frontend (plain HTML/CSS/JS, no build step)
tests/bills/
```

### Reused from existing code

- `db` connection layer (read session for lookups)
- `logic/chat/audit.py` `AuditLog` for the audit trail
- DevCare's stage → confirm → write safety pattern and pending-store approach

### New writable connection

Purchase documents for the IT company live in **DevDB**, whose mirror is **ForumSI**.
A new writable login targets ForumSI, via a new env var (e.g. `BILLS_WRITE_DATABASE_URL`),
separate from DevCare's `DEVCARE_WRITE_DATABASE_URL`.

## Enterprise document — `business_rules/bills/purchase_invoice.yaml`

The source of truth for how a bill maps to the ERP: target tables, field mappings,
draft/uncertified defaults, and matching config. Editing the mapping or the TipoDoc
is a document edit, not a code change.

```yaml
document: purchase_invoice
version: 1
header:
  table: Doc001              # (or FO — verified against live DB first; see Open Items)
  primary_key: Chave
  tipo_doc: { resolve_by: code, code: "VFA" }   # purchase-invoice TipoDoc, resolved at runtime
  draft_defaults: { Estado: 0, ATCUD: "", CodigoAT: "", Certificacao: "" }
  audit_columns: { created_at: DC, created_by: OC }
  fields:
    supplier:  { column: Entidade, source: supplier.match, required: true }
    doc_date:  { column: Data, source: bill.issue_date, required: true }
    due_date:  { column: Vencimento, source: bill.due_date }
    supplier_ref: { column: VRef, source: bill.number }   # supplier's own invoice no.
    net:   { column: Iliquido, source: bill.net_total }
    vat:   { column: IVA, source: bill.vat_total }
    total: { column: Total, source: bill.gross_total, required: true }
    notes: { column: Obs, source: bill.notes }
lines:
  table: LinDoc001
  parent_fk: Documento
  fields:
    article:   { column: ChaveProd, source: line.match }
    description:{ column: Descricao, source: line.description, required: true }
    quantity:  { column: Quantidade, source: line.quantity }
    unit_price:{ column: Punit, source: line.unit_price }
    vat_rate:  { column: Iva, source: line.vat_rate }
    line_total:{ column: Valor, source: line.total }
matching:
  supplier: { table: Entidades, tipo: supplier, match_on: [tax_id, name], create: true }
  article:  { table: Artigos, match_on: [code, barcode, name], create: true }
```

## Extraction pipeline — `logic/bills/extract/`

**`ocr.py`** — `pdf_to_text(pdf_bytes) -> list[PageText]`. Uses `pdf2image` (Poppler) to
rasterize each page, then `pytesseract` per page. Returns page-tagged text so the parser
can cite page numbers. Isolated behind one function so a later "feed the page image to
Claude alongside the OCR text" upgrade is a single-file change.

**`parser.py`** — `parse_bill(pages_text) -> Bill`. One Claude call, low temperature, with
the enterprise document's field list injected so extraction targets exactly what we map.
Returns strict JSON validated into Pydantic. Also runs an **arithmetic sanity check**
(Σ line totals + VAT ≈ gross) and records mismatches as warnings, not hard failures.

```python
class BillLine(BaseModel):
    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    vat_rate: Decimal | None
    total: Decimal | None

class Bill(BaseModel):
    supplier_name: str
    supplier_tax_id: str | None
    number: str | None            # supplier's invoice number
    issue_date: date | None
    due_date: date | None
    currency: str | None
    net_total: Decimal | None
    vat_total: Decimal | None
    gross_total: Decimal | None
    lines: list[BillLine]
    confidence: dict[str, float]  # per-field, drives UI highlighting
```

## Matching engine — `logic/bills/matching.py`

Read-only lookups via the existing read session. Supplier: exact tax-id match first,
then fuzzy name match, returning scored candidates. Each line: match `Artigos` by
code/barcode, then name. No writes happen here — matching only *proposes*.

```python
class MatchResult(BaseModel):
    status: Literal["matched", "ambiguous", "new"]
    chave: int | None                 # set when matched
    candidates: list[Candidate]       # for ambiguous, operator picks
    proposed_new: dict | None         # field values if we'd create it
```

`"new"` means "we will create this on accept, if the operator confirms."

## Proposal → stage → commit lifecycle

Three endpoints, staged so nothing touches the DB until the final confirm.

1. **`POST /bills/upload`** (multipart PDF) → OCR → parse → match → returns a
   **`BillProposal`** (extracted bill + match results + draft `Doc001`/`LinDoc001`
   preview). Stored server-side in the pending store keyed by `proposal_id`. Nothing written.
2. **`POST /bills/stage/{proposal_id}`** — the operator's edited/confirmed proposal returns;
   validated against the YAML rules (required fields, types, every "new" record explicitly
   confirmed). Returns the final write plan or field-level violations.
3. **`POST /bills/commit/{proposal_id}`** — executes the write plan in **one transaction**
   on the ForumSI mirror:
   - create confirmed-new `Entidade` (supplier) and `Artigos`, capturing new `Chave`s
   - insert `Doc001` header (draft: `Estado=0`, ATCUD/certification blank) → get `Chave`
   - insert `LinDoc001` lines with `Documento` = that `Chave`
   - all-or-nothing; on any error, rollback and report which step failed

Every commit appends to the audit log: operator, timestamp, `proposal_id`, rule document +
version applied, and every row created with its new PK.

**Numbering caveat (draft-safe):** we do *not* touch the fiscal `Numeradores` sequence for
drafts. The header's human `Codigo` is left blank/temporary; a human assigns the real number
when finalizing the draft in the ERP. This keeps the feature clear of the certification machinery.

## UI — `ui/bills/`

Single-page, standalone, DevCare's plain HTML/CSS/JS style (no build step, no-cache asset serving).

- **Upload zone** — drag/drop or pick a PDF; shows OCR/extraction progress.
- **Review form** — rendered from the `BillProposal`:
  - Header card: supplier (match badge — ✅ matched / ⚠ ambiguous picker / ➕ new), invoice
    number, dates, totals. Low-confidence fields highlighted.
  - **Line-item table**: description, qty, unit price, VAT, total, and a per-line match cell
    (matched article / pick candidate / create new). Editable inline.
  - Running totals check (extracted vs. sum of lines) with a warning chip on disagreement.
- **Accept** — stage → on success, commit → shows the created draft document's IDs/reference.
  A "will create" section lists any new supplier/article above Accept for explicit confirmation.

## Error handling

- **OCR/Tesseract missing or fails** → clear config error (like DevCare's key handling),
  never a stack trace to the user.
- **Unparseable/low-confidence extraction** → still show the form with what was extracted;
  operator fills gaps. Never auto-write on low confidence.
- **Arithmetic mismatch** → warning; operator must acknowledge or fix before Accept.
- **Write failure** → transaction rollback, nothing partially created, error surfaced with the
  failing step.
- **Duplicate bill** (same supplier + invoice number already staged/written) → warn before commit.

## Testing — `tests/bills/`

- **Extraction**: parser fed canned OCR text fixtures → asserts `Bill` structure and the
  arithmetic-check behavior (Claude call mocked; deterministic).
- **Matching**: seeded lookup data → asserts matched / ambiguous / new outcomes for suppliers
  and articles.
- **Write executor**: against a rolled-back transaction (or test DB) → asserts correct
  multi-table insert order, parent-FK wiring, draft defaults applied, and rollback-on-error
  leaves nothing behind.
- **Rules/validation**: staging rejects missing required fields and unconfirmed "new" records,
  and asserts *which* rule/document was applied.
- **Endpoint smoke**: upload → stage → commit happy path with mocked Claude + a rolled-back
  DB session.

## Open items (verify during implementation, do not assume)

1. **Target table for purchase docs** — whether supplier invoices belong in `Doc001` or the
   separate `FO` table (9,630 rows). Resolve by introspecting the live DB before the first
   write. Design is unchanged either way; only the YAML target table/mapping differs.
2. **Purchase `TipoDoc` code** — the exact code for a purchase invoice, resolved by inspecting
   `TiposDoc` against the live DB.
3. **New writable login** — `BILLS_WRITE_DATABASE_URL` scoped to ForumSI, ideally limited to the
   tables this feature writes (`Doc001`, `LinDoc001`, `Entidades`, `Artigos`).

## Constraints honored

- **AI authoritative for business logic** — mapping + validation live in the enterprise document.
- **Writes flow UI → logic → db** — UI never writes; the service layer validates and the write
  executor is the only writer.
- **Audit trail** — every created row logged with operator, timestamp, and rule version.
- **New domain first-document** — enterprise document precedes logic and UI, per CLAUDE.md.
