# Bill OCR Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone interface that ingests a supplier bill PDF, OCRs it, uses Claude to extract structured data, matches supplier/articles against the ERP, and writes a draft purchase document to the ForumSI mirror after operator confirmation.

**Architecture:** A new `logic/bills/` domain modeled on the existing DevCare module. A pipeline (OCR → Claude parse → match → propose) produces a `BillProposal`; the operator reviews/edits it in a form; on Accept the service validates against an enterprise document (`business_rules/bills/purchase_invoice.yaml`) and a multi-table write executor inserts `Entidades`/`Artigos` (if new), then `Doc001` + `LinDoc001` in one transaction as a draft. Every commit is audited.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy (SQL Server via pyodbc), Anthropic SDK (`claude-sonnet-4-6`), Tesseract via `pytesseract` + `pdf2image`, pytest.

## Global Constraints

- Python `>=3.12,<3.14`; match existing style (`from __future__ import annotations`, 4-space indent, no build step for UI).
- **Writes flow UI → logic → db only.** The UI never issues SQL; the service validates, the executor is the only writer.
- **All SQL identifiers (tables, columns) come from the rule document, never from user/AI input; all values are bound parameters.** (Mirror `logic/devcare/write_executor.py`.)
- **Writes target the ForumSI mirror**, `Doc001` as draft: `Estado=0`, `ATCUD`/`CodigoAT`/`Certificacao` blank. Never touch `Numeradores`.
- **Every commit appends one audit entry** with operator, timestamp, `proposal_id`, rule doc + version, and every created row's PK.
- Write DB session comes from a new `db/bills_connection.py` reading `BILLS_WRITE_DATABASE_URL`; read lookups use the existing `db.connection.get_session`.
- `table_prefix` is `"ForumSI.dbo."` in production and `""` in tests (mirror DevCare's `WriteExecutor`).
- Model id: `claude-sonnet-4-6`.
- Run tests with `pytest tests/bills/ -v`.

---

## File Structure

```
business_rules/bills/purchase_invoice.yaml   # enterprise document (source of truth)
logic/bills/__init__.py
logic/bills/models.py            # Bill, BillLine, PageText, Candidate, MatchResult, BillProposal, WritePlan, arithmetic_warnings
logic/bills/rules/__init__.py
logic/bills/rules/models.py      # PurchaseInvoiceRule + sub-models
logic/bills/rules/loader.py      # RuleLoader -> PurchaseInvoiceRule
logic/bills/extract/__init__.py
logic/bills/extract/ocr.py       # pdf_to_text(pdf_bytes) -> list[PageText]
logic/bills/extract/parser.py    # BillParser.parse(pages) -> Bill
logic/bills/matching.py          # Matcher.match_supplier / match_line
logic/bills/pending.py           # PendingProposalStore
logic/bills/write_executor.py    # BillWriteExecutor.execute(plan, rule) -> dict
logic/bills/audit_writer.py      # BillAuditWriter.record(...)
logic/bills/service.py           # BillService: upload / stage / commit
logic/bills/app.py               # FastAPI app + endpoints + static UI
db/bills_connection.py           # get_bills_write_session()
ui/bills/index.html
ui/bills/app.js
ui/bills/bills.css
tests/bills/__init__.py
tests/bills/... (one test module per task)
```

---

## Task 0: Verify DB write target and TipoDoc code

**Files:**
- Modify: `business_rules/bills/purchase_invoice.yaml` (created in Task 1; if running Task 0 first, record findings in a scratch note and apply during Task 1)

This task resolves the two spec open items before any write code assumes them. It is investigation, not TDD.

- [ ] **Step 1: Introspect the purchase document type**

With `DATABASE_URL` set to the read-only login, run (adjust database to `DevDB`):

```bash
python -c "import os; from sqlalchemy import create_engine, text; e=create_engine(os.environ['DATABASE_URL']); import json; \
print(json.dumps([dict(r._mapping) for r in e.connect().execute(text(\"SELECT Chave, Codigo, Nome, Abreviatura FROM DevDB.dbo.TiposDoc WHERE Nome LIKE '%ompr%' OR Nome LIKE '%ornec%' OR Codigo LIKE 'V%'\"))], default=str, indent=2))"
```

Expected: rows for purchase/supplier document types. Record the `Codigo` of the purchase-invoice type (e.g. `VFA`).

- [ ] **Step 2: Confirm whether purchase docs live in `Doc001` or `FO`**

```bash
python -c "import os; from sqlalchemy import create_engine, text; e=create_engine(os.environ['DATABASE_URL']); \
r=e.connect().execute(text(\"SELECT COUNT(*) FROM DevDB.dbo.Doc001 d JOIN DevDB.dbo.TiposDoc t ON d.TipoDoc=t.Chave WHERE t.Codigo=:c\"), {'c':'VFA'}); print('Doc001 purchase rows:', r.scalar())"
```

Expected: a non-zero count confirms purchase invoices are stored in `Doc001` under that TipoDoc. If zero, inspect the `FO` table columns and treat `FO` as the header table instead (the design is unchanged; only `header.table` and `header.fields` columns in the YAML differ).

- [ ] **Step 3: Record findings**

Write the confirmed `header.table` and `tipo_doc.code` into `business_rules/bills/purchase_invoice.yaml` in Task 1. If the DB is unreachable in this environment, proceed with the documented defaults (`table: Doc001`, `code: "VFA"`) and add a `# UNVERIFIED` comment on those two lines so a reviewer knows to confirm.

- [ ] **Step 4: Commit**

```bash
git add business_rules/bills/purchase_invoice.yaml
git commit -m "chore(bills): record verified purchase-doc target and TipoDoc"
```

---

## Task 1: Enterprise document + rule models + loader

**Files:**
- Create: `business_rules/bills/purchase_invoice.yaml`
- Create: `logic/bills/__init__.py` (empty), `logic/bills/rules/__init__.py` (empty)
- Create: `logic/bills/rules/models.py`
- Create: `logic/bills/rules/loader.py`
- Create: `tests/bills/__init__.py` (empty)
- Test: `tests/bills/test_rules.py`

**Interfaces:**
- Produces: `PurchaseInvoiceRule` with `.document: str`, `.version: int`, `.header: HeaderRule`, `.lines: LinesRule`, `.matching: MatchingRule`.
  - `HeaderRule`: `.table: str`, `.primary_key: str`, `.tipo_doc: TipoDocRef`, `.draft_defaults: dict`, `.audit_columns: dict`, `.fields: dict[str, HeaderFieldRule]`
  - `HeaderFieldRule`/`LineFieldRule`: `.column: str`, `.source: str`, `.required: bool`
  - `LinesRule`: `.table: str`, `.parent_fk: str`, `.fields: dict[str, LineFieldRule]`
  - `TipoDocRef`: `.resolve_by: str`, `.code: str`
  - `MatchingRule`: `.supplier: MatchTargetRule`, `.article: MatchTargetRule`
  - `MatchTargetRule`: `.table: str`, `.tipo: str | None`, `.match_on: list[str]`, `.create: bool`
- Produces: `RuleLoader(directory).rule() -> PurchaseInvoiceRule`

- [ ] **Step 1: Write the enterprise document**

Create `business_rules/bills/purchase_invoice.yaml`:

```yaml
document: purchase_invoice
version: 1
header:
  table: Doc001
  primary_key: Chave
  tipo_doc: { resolve_by: code, code: "31" }   # 31 = "V/ Factura" (Vossa Factura = supplier invoice); verified in DevDB, 2341 docs in Doc001
  draft_defaults: { Estado: 0, ATCUD: "", CodigoAT: "", Certificacao: "" }
  audit_columns: { created_at: DC, created_by: OC }
  fields:
    supplier:  { column: Entidade, source: supplier.match, required: true }
    doc_date:  { column: Data, source: bill.issue_date, required: true }
    due_date:  { column: Vencimento, source: bill.due_date }
    supplier_ref: { column: VRef, source: bill.number }
    net:   { column: Iliquido, source: bill.net_total }
    vat:   { column: IVA, source: bill.vat_total }
    total: { column: Total, source: bill.gross_total, required: true }
    notes: { column: Obs, source: bill.notes }
lines:
  table: LinDoc001
  parent_fk: Documento
  fields:
    article:    { column: ChaveProd, source: line.match }
    description:{ column: Descricao, source: line.description, required: true }
    quantity:  { column: Quantidade, source: line.quantity }
    unit_price:{ column: Punit, source: line.unit_price }
    vat_rate:  { column: Iva, source: line.vat_rate }
    line_total:{ column: Valor, source: line.total }
matching:
  supplier: { table: Entidades, tipo: supplier, match_on: [tax_id, name], create: true }
  article:  { table: Artigos, match_on: [code, barcode, name], create: true }
```

- [ ] **Step 2: Write the failing test**

Create `tests/bills/test_rules.py`:

```python
from pathlib import Path
from logic.bills.rules.loader import RuleLoader

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


def test_loads_purchase_invoice_rule():
    rule = RuleLoader(RULES_DIR).rule()
    assert rule.document == "purchase_invoice"
    assert rule.header.table in ("Doc001", "FO")
    assert rule.header.tipo_doc.code
    assert rule.header.fields["total"].required is True
    assert rule.header.fields["total"].column == "Total"
    assert rule.lines.parent_fk == "Documento"
    assert rule.matching.supplier.create is True
    assert "tax_id" in rule.matching.supplier.match_on
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/bills/test_rules.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'logic.bills'`

- [ ] **Step 4: Write the rule models**

Create `logic/bills/rules/models.py`:

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict


class TipoDocRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resolve_by: Literal["code"]
    code: str


class HeaderFieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str
    source: str
    required: bool = False


class LineFieldRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: str
    source: str
    required: bool = False


class HeaderRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    primary_key: str
    tipo_doc: TipoDocRef
    draft_defaults: dict[str, int | str] = {}
    audit_columns: dict[str, str] = {}
    fields: dict[str, HeaderFieldRule]


class LinesRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    parent_fk: str
    fields: dict[str, LineFieldRule]


class MatchTargetRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: str
    tipo: str | None = None
    match_on: list[str]
    create: bool = False


class MatchingRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier: MatchTargetRule
    article: MatchTargetRule


class PurchaseInvoiceRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document: str
    version: int
    header: HeaderRule
    lines: LinesRule
    matching: MatchingRule
```

- [ ] **Step 5: Write the loader**

Create `logic/bills/rules/loader.py`:

```python
from __future__ import annotations
from pathlib import Path

import yaml

from logic.bills.rules.models import PurchaseInvoiceRule


class RuleLoader:
    """Loads the single purchase_invoice.yaml enterprise document."""

    def __init__(self, directory: Path | str) -> None:
        self._path = Path(directory) / "purchase_invoice.yaml"
        data = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        self._rule = PurchaseInvoiceRule.model_validate(data)

    def rule(self) -> PurchaseInvoiceRule:
        return self._rule
```

Also create empty `logic/bills/__init__.py`, `logic/bills/rules/__init__.py`, `tests/bills/__init__.py`.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/bills/test_rules.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add business_rules/bills/ logic/bills/__init__.py logic/bills/rules/ tests/bills/__init__.py tests/bills/test_rules.py
git commit -m "feat(bills): add purchase-invoice enterprise document, rule models and loader"
```

---

## Task 2: Bill domain models + arithmetic check

**Files:**
- Create: `logic/bills/models.py`
- Test: `tests/bills/test_models.py`

**Interfaces:**
- Produces (all Pydantic v2 `BaseModel`, `Decimal`/`date` typed):
  - `PageText(page: int, text: str)`
  - `BillLine(description: str, quantity: Decimal|None, unit_price: Decimal|None, vat_rate: Decimal|None, total: Decimal|None)`
  - `Bill(supplier_name, supplier_tax_id, number, issue_date, due_date, currency, net_total, vat_total, gross_total, lines: list[BillLine], confidence: dict[str,float])`
  - `Candidate(chave: int, label: str, score: float)`
  - `MatchResult(status: Literal["matched","ambiguous","new"], chave: int|None, candidates: list[Candidate], proposed_new: dict|None, confirmed: bool)`
  - `BillProposal(proposal_id: str, bill: Bill, supplier_match: MatchResult, line_matches: list[MatchResult], warnings: list[str])`
  - `WritePlan(proposal_id, supplier: MatchResult, header: dict, lines: list[LinePlan], rule_doc: str, rule_version: int)`
  - `LinePlan(article: MatchResult, columns: dict)`
  - `arithmetic_warnings(bill: Bill) -> list[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_models.py`:

```python
from decimal import Decimal
from logic.bills.models import Bill, BillLine, arithmetic_warnings


def _bill(**kw):
    base = dict(supplier_name="ACME", net_total=Decimal("100"),
                vat_total=Decimal("23"), gross_total=Decimal("123"),
                lines=[BillLine(description="X", quantity=Decimal("1"),
                                unit_price=Decimal("100"), vat_rate=Decimal("23"),
                                total=Decimal("100"))])
    base.update(kw)
    return Bill(**base)


def test_no_warning_when_totals_consistent():
    assert arithmetic_warnings(_bill()) == []


def test_warning_when_gross_mismatches_net_plus_vat():
    warnings = arithmetic_warnings(_bill(gross_total=Decimal("200")))
    assert any("gross" in w.lower() for w in warnings)


def test_warning_when_line_totals_do_not_sum_to_net():
    b = _bill(lines=[BillLine(description="X", total=Decimal("40"))])
    warnings = arithmetic_warnings(b)
    assert any("line" in w.lower() for w in warnings)


def test_missing_totals_produce_no_arithmetic_warning():
    b = _bill(net_total=None, vat_total=None, gross_total=None,
              lines=[BillLine(description="X")])
    assert arithmetic_warnings(b) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bills/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'logic.bills.models'`

- [ ] **Step 3: Write the models**

Create `logic/bills/models.py`:

```python
from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class PageText(BaseModel):
    page: int
    text: str


class BillLine(BaseModel):
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    vat_rate: Decimal | None = None
    total: Decimal | None = None


class Bill(BaseModel):
    supplier_name: str
    supplier_tax_id: str | None = None
    number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    net_total: Decimal | None = None
    vat_total: Decimal | None = None
    gross_total: Decimal | None = None
    lines: list[BillLine] = []
    confidence: dict[str, float] = {}


class Candidate(BaseModel):
    chave: int
    label: str
    score: float


class MatchResult(BaseModel):
    status: Literal["matched", "ambiguous", "new"]
    chave: int | None = None
    candidates: list[Candidate] = []
    proposed_new: dict | None = None
    confirmed: bool = False


class BillProposal(BaseModel):
    proposal_id: str
    bill: Bill
    supplier_match: MatchResult
    line_matches: list[MatchResult] = []
    warnings: list[str] = []


class LinePlan(BaseModel):
    article: MatchResult
    columns: dict


class WritePlan(BaseModel):
    proposal_id: str
    supplier: MatchResult
    header: dict
    lines: list[LinePlan]
    rule_doc: str
    rule_version: int


_TOL = Decimal("0.02")


def arithmetic_warnings(bill: Bill) -> list[str]:
    """Flag internal inconsistencies without failing; the operator resolves them."""
    warnings: list[str] = []
    if bill.net_total is not None and bill.vat_total is not None \
            and bill.gross_total is not None:
        if abs((bill.net_total + bill.vat_total) - bill.gross_total) > _TOL:
            warnings.append(
                f"gross_total {bill.gross_total} != net {bill.net_total} + vat {bill.vat_total}")
    line_totals = [ln.total for ln in bill.lines if ln.total is not None]
    if line_totals and bill.net_total is not None:
        summed = sum(line_totals, Decimal("0"))
        if abs(summed - bill.net_total) > _TOL:
            warnings.append(
                f"sum of line totals {summed} != net_total {bill.net_total}")
    return warnings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/bills/test_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logic/bills/models.py tests/bills/test_models.py
git commit -m "feat(bills): add bill/proposal/write-plan models and arithmetic check"
```

---

## Task 3: OCR wrapper

**Files:**
- Create: `logic/bills/extract/__init__.py` (empty)
- Create: `logic/bills/extract/ocr.py`
- Modify: `pyproject.toml` (add `pytesseract`, `pdf2image`, `pillow`)
- Test: `tests/bills/test_ocr.py`

**Interfaces:**
- Produces: `pdf_to_text(pdf_bytes: bytes, *, dpi: int = 300) -> list[PageText]`
- Produces: `class OcrUnavailable(RuntimeError)` — raised when Tesseract/Poppler are not installed.

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, append to `dependencies`:

```toml
    "pytesseract>=0.3.10",
    "pdf2image>=1.17.0",
    "pillow>=10.0.0",
```

Note (record in commit body): the host also needs the Tesseract binary and Poppler (`apt-get install -y tesseract-ocr poppler-utils`); this must be added to the Render build before deploy.

- [ ] **Step 2: Write the failing test**

Create `tests/bills/test_ocr.py` (mocks the two third-party calls so no binaries are needed in CI):

```python
import sys
import types
import pytest
from logic.bills import extract


def _install_fakes(monkeypatch, pages_text, raise_exc=None):
    fake_p2i = types.ModuleType("pdf2image")
    fake_tess = types.ModuleType("pytesseract")

    def convert_from_bytes(_bytes, dpi=300):
        if raise_exc:
            raise raise_exc
        return [f"IMG{i}" for i in range(len(pages_text))]

    def image_to_string(img):
        return pages_text[int(str(img)[3:])]

    fake_p2i.convert_from_bytes = convert_from_bytes
    fake_tess.image_to_string = image_to_string
    monkeypatch.setitem(sys.modules, "pdf2image", fake_p2i)
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tess)


def test_pdf_to_text_returns_page_tagged_text(monkeypatch):
    from logic.bills.extract import ocr
    _install_fakes(monkeypatch, ["hello", "world"])
    pages = ocr.pdf_to_text(b"%PDF-fake")
    assert [p.page for p in pages] == [1, 2]
    assert pages[0].text == "hello" and pages[1].text == "world"


def test_pdf_to_text_raises_ocr_unavailable_on_missing_binary(monkeypatch):
    from logic.bills.extract import ocr
    _install_fakes(monkeypatch, [], raise_exc=OSError("poppler not found"))
    with pytest.raises(ocr.OcrUnavailable):
        ocr.pdf_to_text(b"%PDF-fake")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/bills/test_ocr.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'logic.bills.extract'`

- [ ] **Step 4: Write the OCR wrapper**

Create `logic/bills/extract/__init__.py` (empty) and `logic/bills/extract/ocr.py`:

```python
from __future__ import annotations

from logic.bills.models import PageText


class OcrUnavailable(RuntimeError):
    """Tesseract or Poppler is not installed/reachable on the host."""


def pdf_to_text(pdf_bytes: bytes, *, dpi: int = 300) -> list[PageText]:
    """Rasterize each PDF page and OCR it. Imports are function-local so the
    module loads even where the binaries are absent (they're only needed at call
    time). Feeding the page image to Claude alongside this text is a future
    drop-in: keep this the single extraction entry point."""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError as e:  # pragma: no cover - packaging guard
        raise OcrUnavailable(str(e)) from e
    try:
        images = convert_from_bytes(pdf_bytes, dpi=dpi)
        return [PageText(page=i + 1, text=pytesseract.image_to_string(img))
                for i, img in enumerate(images)]
    except (OSError, RuntimeError) as e:
        raise OcrUnavailable(str(e)) from e
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/bills/test_ocr.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml logic/bills/extract/ tests/bills/test_ocr.py
git commit -m "feat(bills): add Tesseract OCR wrapper (pdf_to_text)"
```

---

## Task 4: Claude bill parser

**Files:**
- Create: `logic/bills/extract/parser.py`
- Test: `tests/bills/test_parser.py`

**Interfaces:**
- Consumes: `list[PageText]` (Task 2/3), `PurchaseInvoiceRule` (Task 1), `Bill` (Task 2).
- Produces: `class BillParser` with `__init__(self, anthropic_client, model: str, rule: PurchaseInvoiceRule)` and `parse(self, pages: list[PageText]) -> Bill`.
- Produces: module function `field_hint(rule: PurchaseInvoiceRule) -> str` (the human-readable list of fields to extract, injected into the prompt).

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_parser.py`:

```python
import json
from pathlib import Path
from logic.bills.extract.parser import BillParser, field_hint
from logic.bills.models import PageText
from logic.bills.rules.loader import RuleLoader

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


class _FakeContent:
    def __init__(self, text): self.type = "text"; self.text = text


class _FakeResponse:
    def __init__(self, text): self.content = [_FakeContent(text)]


class _FakeAnthropic:
    def __init__(self, payload): self._payload = payload; self.messages = self
    def create(self, **kw):
        self.last_kwargs = kw
        return _FakeResponse(json.dumps(self._payload))


def _rule():
    return RuleLoader(RULES_DIR).rule()


def test_field_hint_lists_expected_fields():
    hint = field_hint(_rule())
    assert "issue_date" in hint and "gross_total" in hint and "description" in hint


def test_parse_returns_bill_from_model_json():
    payload = {"supplier_name": "ACME LDA", "supplier_tax_id": "500100200",
               "number": "FT 2026/17", "issue_date": "2026-06-01",
               "net_total": "100.00", "vat_total": "23.00", "gross_total": "123.00",
               "lines": [{"description": "Widget", "quantity": "2",
                          "unit_price": "50.00", "vat_rate": "23", "total": "100.00"}]}
    client = _FakeAnthropic(payload)
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    bill = parser.parse([PageText(page=1, text="raw ocr text")])
    assert bill.supplier_name == "ACME LDA"
    assert str(bill.gross_total) == "123.00"
    assert len(bill.lines) == 1 and bill.lines[0].description == "Widget"
    # OCR text is passed to the model
    assert "raw ocr text" in json.dumps(client.last_kwargs["messages"], default=str)


def test_parse_tolerates_json_wrapped_in_prose():
    payload = {"supplier_name": "X", "lines": []}
    text = "Here is the data:\n```json\n" + json.dumps(payload) + "\n```"

    class Wrapped(_FakeAnthropic):
        def create(self, **kw):
            return _FakeResponse(text)

    parser = BillParser(Wrapped({}), "claude-sonnet-4-6", _rule())
    bill = parser.parse([PageText(page=1, text="t")])
    assert bill.supplier_name == "X"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bills/test_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'logic.bills.extract.parser'`

- [ ] **Step 3: Write the parser**

Create `logic/bills/extract/parser.py`:

```python
from __future__ import annotations
import json
import re
from typing import Any

from logic.bills.models import Bill, PageText
from logic.bills.rules.models import PurchaseInvoiceRule

_SYSTEM = (
    "You extract structured data from a supplier invoice. You are given the raw "
    "OCR text of the invoice pages. Return ONLY a JSON object with these keys: "
    "supplier_name, supplier_tax_id, number, issue_date (YYYY-MM-DD), due_date "
    "(YYYY-MM-DD), currency, net_total, vat_total, gross_total, and lines (a list "
    "of objects with description, quantity, unit_price, vat_rate, total). Use null "
    "for anything not present. Amounts as decimal strings without currency symbols. "
    "Do not invent values."
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def field_hint(rule: PurchaseInvoiceRule) -> str:
    # Emit the Bill/line OUTPUT field names (from each field's source, e.g.
    # bill.issue_date -> issue_date) so the hint matches the JSON keys Claude
    # must return; skip the .match sources (resolved by the executor).
    def _out_names(fields) -> str:
        names = [fr.source.split(".", 1)[1]
                 for fr in fields.values()
                 if not fr.source.endswith(".match")]
        return ", ".join(names)
    header = _out_names(rule.header.fields)
    lines = _out_names(rule.lines.fields)
    return f"Header fields: {header}. Line fields: {lines}."


def _extract_json(text: str) -> dict[str, Any]:
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError("model returned no JSON object")
    return json.loads(m.group(0))


class BillParser:
    def __init__(self, anthropic_client: Any, model: str,
                 rule: PurchaseInvoiceRule) -> None:
        self._client = anthropic_client
        self._model = model
        self._rule = rule

    def parse(self, pages: list[PageText]) -> Bill:
        joined = "\n\n".join(f"--- page {p.page} ---\n{p.text}" for p in pages)
        user = f"{field_hint(self._rule)}\n\nOCR TEXT:\n{joined}"
        resp = self._client.messages.create(
            model=self._model, max_tokens=2048, temperature=0,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(c, "text", "") for c in resp.content
                       if getattr(c, "type", None) == "text")
        return Bill.model_validate(_extract_json(text))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/bills/test_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logic/bills/extract/parser.py tests/bills/test_parser.py
git commit -m "feat(bills): add Claude bill parser (OCR text -> Bill)"
```

---

## Task 5: Matching engine

**Files:**
- Create: `logic/bills/matching.py`
- Test: `tests/bills/test_matching.py`

**Interfaces:**
- Consumes: `Bill`, `BillLine`, `MatchResult`, `Candidate` (Task 2); `PurchaseInvoiceRule` (Task 1).
- Produces: `class Matcher` with `__init__(self, reader, rule, *, table_prefix: str = "")` where `reader(sql: str, params: dict) -> list[dict]`, and methods `match_supplier(self, bill: Bill) -> MatchResult` and `match_line(self, line: BillLine) -> MatchResult`.
- Matching policy: supplier — exact tax-id match ⇒ `matched`; else name candidates (case-insensitive `LIKE`), 1 ⇒ `matched`, >1 ⇒ `ambiguous`, 0 ⇒ `new` with `proposed_new` (Nome, NCont). Line — code/barcode exact ⇒ `matched`; else name candidates same rule; 0 ⇒ `new` with `proposed_new` (Nome).

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_matching.py`:

```python
from decimal import Decimal
from pathlib import Path
from logic.bills.matching import Matcher
from logic.bills.models import Bill, BillLine
from logic.bills.rules.loader import RuleLoader

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


class FakeReader:
    """Answers by inspecting bound params, not SQL text."""
    def __init__(self, entidades=None, artigos=None):
        self._ents = entidades or []
        self._arts = artigos or []

    def __call__(self, sql, params):
        p = params or {}
        if "Entidades" in sql:
            if "NCont" in sql and "tax_id" in p:
                return [r for r in self._ents if r["NCont"] == p["tax_id"]]
            if "name" in p:
                needle = p["name"].strip("%").lower()
                return [r for r in self._ents if needle in r["Nome"].lower()]
        if "Artigos" in sql:
            needle = (p.get("name") or "").strip("%").lower()
            return [r for r in self._arts if needle and needle in r["Nome"].lower()]
        return []


def _rule():
    return RuleLoader(RULES_DIR).rule()


def _bill(**kw):
    return Bill(supplier_name=kw.get("supplier_name", "ACME"),
               supplier_tax_id=kw.get("supplier_tax_id"))


def test_supplier_matched_by_tax_id():
    reader = FakeReader(entidades=[{"Chave": 7, "Nome": "ACME LDA", "NCont": "500100200"}])
    m = Matcher(reader, _rule())
    res = m.match_supplier(_bill(supplier_tax_id="500100200"))
    assert res.status == "matched" and res.chave == 7


def test_supplier_ambiguous_by_name():
    reader = FakeReader(entidades=[{"Chave": 1, "Nome": "ACME LDA", "NCont": "x"},
                                   {"Chave": 2, "Nome": "ACME PORTO", "NCont": "y"}])
    m = Matcher(reader, _rule())
    res = m.match_supplier(_bill(supplier_name="ACME"))
    assert res.status == "ambiguous" and len(res.candidates) == 2


def test_supplier_new_when_no_match():
    m = Matcher(FakeReader(), _rule())
    res = m.match_supplier(_bill(supplier_name="Nobody", supplier_tax_id="999888777"))
    assert res.status == "new"
    assert res.proposed_new["Nome"] == "Nobody"
    assert res.proposed_new["NCont"] == "999888777"


def test_line_new_when_no_article_match():
    m = Matcher(FakeReader(), _rule())
    res = m.match_line(BillLine(description="Mystery Widget"))
    assert res.status == "new" and res.proposed_new["Nome"] == "Mystery Widget"


def test_line_matched_by_name():
    reader = FakeReader(artigos=[{"Chave": 42, "Nome": "Widget", "Codigo": "W1"}])
    m = Matcher(reader, _rule())
    res = m.match_line(BillLine(description="Widget"))
    assert res.status == "matched" and res.chave == 42
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bills/test_matching.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'logic.bills.matching'`

- [ ] **Step 3: Write the matcher**

Create `logic/bills/matching.py`:

```python
from __future__ import annotations
from typing import Callable

from logic.bills.models import Bill, BillLine, Candidate, MatchResult
from logic.bills.rules.models import PurchaseInvoiceRule

Reader = Callable[[str, dict], list[dict]]


class Matcher:
    """Read-only supplier/article matching. Never writes; 'new' means the
    service will offer to create the record on the operator's confirmation."""

    def __init__(self, reader: Reader, rule: PurchaseInvoiceRule, *,
                 table_prefix: str = "") -> None:
        self._read = reader
        self._rule = rule
        self._p = table_prefix

    def match_supplier(self, bill: Bill) -> MatchResult:
        ent = self._rule.matching.supplier.table
        if bill.supplier_tax_id:
            rows = self._read(
                f"SELECT Chave, Nome, NCont FROM {self._p}{ent} WHERE NCont = :tax_id",
                {"tax_id": bill.supplier_tax_id})
            if len(rows) == 1:
                return MatchResult(status="matched", chave=int(rows[0]["Chave"]))
        rows = self._read(
            f"SELECT Chave, Nome FROM {self._p}{ent} WHERE LOWER(Nome) LIKE :name",
            {"name": f"%{bill.supplier_name.lower()}%"})
        return self._resolve(rows, {"Nome": bill.supplier_name,
                                    "NCont": bill.supplier_tax_id})

    def match_line(self, line: BillLine) -> MatchResult:
        art = self._rule.matching.article.table
        rows = self._read(
            f"SELECT Chave, Nome FROM {self._p}{art} WHERE LOWER(Nome) LIKE :name",
            {"name": f"%{line.description.lower()}%"})
        return self._resolve(rows, {"Nome": line.description})

    @staticmethod
    def _resolve(rows: list[dict], proposed_new: dict) -> MatchResult:
        if len(rows) == 1:
            return MatchResult(status="matched", chave=int(rows[0]["Chave"]))
        if len(rows) > 1:
            cands = [Candidate(chave=int(r["Chave"]), label=str(r["Nome"]), score=1.0)
                     for r in rows]
            return MatchResult(status="ambiguous", candidates=cands)
        return MatchResult(status="new", proposed_new=proposed_new)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/bills/test_matching.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logic/bills/matching.py tests/bills/test_matching.py
git commit -m "feat(bills): add supplier/article matching engine"
```

---

## Task 6: Pending proposal store

**Files:**
- Create: `logic/bills/pending.py`
- Test: `tests/bills/test_pending.py`

**Interfaces:**
- Produces: `class PendingProposalStore` with `put(self, key: str, value) -> None`, `get(self, key: str)`, `pop(self, key: str)`.

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_pending.py`:

```python
from logic.bills.pending import PendingProposalStore


def test_put_get_pop_roundtrip():
    store = PendingProposalStore()
    store.put("p1", {"x": 1})
    assert store.get("p1") == {"x": 1}
    assert store.pop("p1") == {"x": 1}
    assert store.get("p1") is None


def test_pop_missing_returns_none():
    assert PendingProposalStore().pop("nope") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bills/test_pending.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'logic.bills.pending'`

- [ ] **Step 3: Write the store**

Create `logic/bills/pending.py`:

```python
from __future__ import annotations
from typing import Any


class PendingProposalStore:
    """In-memory staging of proposals/write-plans awaiting confirmation.
    Keyed by proposal_id. Single-process, like DevCare's PendingChangeStore."""

    def __init__(self) -> None:
        self._items: dict[str, Any] = {}

    def put(self, key: str, value: Any) -> None:
        self._items[key] = value

    def get(self, key: str) -> Any:
        return self._items.get(key)

    def pop(self, key: str) -> Any:
        return self._items.pop(key, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/bills/test_pending.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logic/bills/pending.py tests/bills/test_pending.py
git commit -m "feat(bills): add pending proposal store"
```

---

## Task 7: Multi-table write executor

**Files:**
- Create: `logic/bills/write_executor.py`
- Test: `tests/bills/test_write_executor.py`

**Interfaces:**
- Consumes: `WritePlan`, `LinePlan`, `MatchResult` (Task 2); `PurchaseInvoiceRule` (Task 1).
- Produces: `class BillWriteExecutor` with `__init__(self, session_factory, *, table_prefix: str = "ForumSI.dbo.", now=..., operator_key: int = 0)` and `execute(self, plan: WritePlan, rule: PurchaseInvoiceRule) -> dict`.
- Returns `{"document_chave": int, "supplier_chave": int, "line_chaves": list[int], "created_supplier": bool, "created_articles": list[int]}`.
- Behavior: one transaction; resolve/create supplier → resolve/create each article → insert header (draft defaults + resolved TipoDoc + Entidade + audit) → insert lines (parent FK + ChaveProd). Any error rolls back the whole transaction.

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_write_executor.py`:

```python
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from logic.bills.models import LinePlan, MatchResult, WritePlan
from logic.bills.rules.loader import RuleLoader
from logic.bills.write_executor import BillWriteExecutor

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


@pytest.fixture
def session_factory(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path/'w.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE TiposDoc (Chave INTEGER, Codigo TEXT)"))
        c.execute(text("INSERT INTO TiposDoc (Chave, Codigo) VALUES (5, '31')"))
        c.execute(text("CREATE TABLE Entidades (Chave INTEGER, Nome TEXT, NCont TEXT, "
                       "Tipo INTEGER, Listar INTEGER, DC TEXT, OC INTEGER)"))
        c.execute(text("INSERT INTO Entidades (Chave, Nome) VALUES (7, 'Existing Supplier')"))
        c.execute(text("CREATE TABLE Artigos (Chave INTEGER, Nome TEXT, Codigo TEXT, "
                       "DC TEXT, OC INTEGER)"))
        c.execute(text("CREATE TABLE Doc001 (Chave INTEGER, TipoDoc INTEGER, Entidade INTEGER, "
                       "Data TEXT, Vencimento TEXT, VRef TEXT, Iliquido NUMERIC, IVA NUMERIC, "
                       "Total NUMERIC, Obs TEXT, Estado INTEGER, ATCUD TEXT, CodigoAT TEXT, "
                       "Certificacao TEXT, DC TEXT, OC INTEGER)"))
        c.execute(text("CREATE TABLE LinDoc001 (Chave INTEGER, Documento INTEGER, "
                       "ChaveProd INTEGER, Descricao TEXT, Quantidade NUMERIC, "
                       "Punit NUMERIC, Iva NUMERIC, Valor NUMERIC)"))
    Local = sessionmaker(bind=eng)

    @contextmanager
    def factory():
        s = Local()
        try:
            yield s; s.commit()
        except Exception:
            s.rollback(); raise
        finally:
            s.close()
    return factory, eng


def _rule():
    return RuleLoader(RULES_DIR).rule()


def _ex(factory):
    return BillWriteExecutor(factory, table_prefix="",
                             now=lambda: "2026-07-08T00:00:00Z", operator_key=0)


def _plan_matched_supplier():
    return WritePlan(
        proposal_id="p1",
        supplier=MatchResult(status="matched", chave=7),
        header={"Data": "2026-06-01", "VRef": "FT 2026/17",
                "Iliquido": "100", "IVA": "23", "Total": "123", "Obs": ""},
        lines=[LinePlan(article=MatchResult(status="matched", chave=42),
                        columns={"Descricao": "Widget", "Quantidade": "2",
                                 "Punit": "50", "Iva": "23", "Valor": "100"})],
        rule_doc="purchase_invoice", rule_version=1)


def test_commit_matched_supplier_and_article(session_factory):
    factory, eng = session_factory
    with eng.begin() as c:
        c.execute(text("INSERT INTO Artigos (Chave, Nome) VALUES (42, 'Widget')"))
    result = _ex(factory).execute(_plan_matched_supplier(), _rule())
    with eng.begin() as c:
        doc = c.execute(text("SELECT * FROM Doc001")).fetchone()
        line = c.execute(text("SELECT * FROM LinDoc001")).fetchone()
    assert result["supplier_chave"] == 7 and result["created_supplier"] is False
    assert doc.Entidade == 7 and doc.TipoDoc == 5 and doc.Estado == 0
    assert doc.ATCUD == "" and doc.Total == 123
    assert line.Documento == result["document_chave"] and line.ChaveProd == 42


def test_commit_creates_new_supplier_and_article(session_factory):
    factory, eng = session_factory
    plan = WritePlan(
        proposal_id="p2",
        supplier=MatchResult(status="new", confirmed=True,
                             proposed_new={"Nome": "New Co", "NCont": "500999999"}),
        header={"Data": "2026-06-01", "VRef": "A1", "Iliquido": "10", "IVA": "2",
                "Total": "12", "Obs": ""},
        lines=[LinePlan(article=MatchResult(status="new", confirmed=True,
                                            proposed_new={"Nome": "New Item"}),
                        columns={"Descricao": "New Item", "Quantidade": "1",
                                 "Punit": "10", "Iva": "23", "Valor": "10"})],
        rule_doc="purchase_invoice", rule_version=1)
    result = _ex(factory).execute(plan, _rule())
    with eng.begin() as c:
        sup = c.execute(text("SELECT Chave, Nome, NCont, Tipo FROM Entidades WHERE Nome='New Co'")).fetchone()
        art = c.execute(text("SELECT Chave, Nome FROM Artigos WHERE Nome='New Item'")).fetchone()
        doc = c.execute(text("SELECT Entidade FROM Doc001")).fetchone()
    assert result["created_supplier"] is True and sup is not None
    assert doc.Entidade == sup.Chave
    assert art.Chave in result["created_articles"]


def test_unconfirmed_new_supplier_is_rejected_and_nothing_written(session_factory):
    factory, eng = session_factory
    plan = _plan_matched_supplier()
    plan.supplier = MatchResult(status="new", confirmed=False,
                                proposed_new={"Nome": "X"})
    with pytest.raises(ValueError, match="not confirmed"):
        _ex(factory).execute(plan, _rule())
    with eng.begin() as c:
        assert c.execute(text("SELECT COUNT(*) FROM Doc001")).scalar() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bills/test_write_executor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'logic.bills.write_executor'`

- [ ] **Step 3: Write the executor**

Create `logic/bills/write_executor.py`:

```python
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

from logic.bills.models import MatchResult, WritePlan
from logic.bills.rules.models import PurchaseInvoiceRule


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class BillWriteExecutor:
    """Writes a WritePlan as one transaction: (optional) new supplier + articles,
    then a draft Doc001 header and its LinDoc001 lines. All identifiers come from
    the rule document; all values are bound parameters."""

    def __init__(self, session_factory: Callable, *,
                 table_prefix: str = "ForumSI.dbo.",
                 now: Callable[[], str] = _now_iso, operator_key: int = 0) -> None:
        self._factory = session_factory
        self._p = table_prefix
        self._now = now
        self._operator_key = operator_key

    def _next_key(self, session, table: str) -> int:
        # Single-writer assumption, as in DevCare's WriteExecutor.
        return int(session.execute(
            text(f"SELECT COALESCE(MAX(Chave), 0) + 1 AS k FROM {self._p}{table}")
        ).scalar())

    def _insert(self, session, table: str, row: dict) -> None:
        cols = ", ".join(row)
        binds = ", ".join(f":{c}" for c in row)
        session.execute(text(f"INSERT INTO {self._p}{table} ({cols}) VALUES ({binds})"), row)

    def _resolve_entity(self, session, match: MatchResult, table: str,
                        defaults: dict) -> tuple[int, bool]:
        if match.status == "matched" and match.chave is not None:
            return match.chave, False
        if not match.confirmed or match.proposed_new is None:
            raise ValueError(f"new {table} record is not confirmed")
        pk = self._next_key(session, table)
        row = {"Chave": pk, **defaults, **match.proposed_new,
               "DC": self._now(), "OC": self._operator_key}
        self._insert(session, table, row)
        return pk, True

    def execute(self, plan: WritePlan, rule: PurchaseInvoiceRule) -> dict[str, Any]:
        with self._factory() as session:
            supplier_defaults = {"Tipo": 2, "Listar": 1}  # Tipo=2: supplier
            supplier_chave, created_supplier = self._resolve_entity(
                session, plan.supplier, rule.matching.supplier.table, supplier_defaults)

            tipo_doc = int(session.execute(
                text(f"SELECT Chave FROM {self._p}TiposDoc WHERE Codigo = :c"),
                {"c": rule.header.tipo_doc.code}).scalar())

            doc_pk = self._next_key(session, rule.header.table)
            header = {"Chave": doc_pk, "TipoDoc": tipo_doc,
                      rule.header.fields["supplier"].column: supplier_chave}
            header.update(rule.header.draft_defaults)
            created_at = rule.header.audit_columns.get("created_at")
            created_by = rule.header.audit_columns.get("created_by")
            if created_at:
                header[created_at] = self._now()
            if created_by:
                header[created_by] = self._operator_key
            header.update(plan.header)
            self._insert(session, rule.header.table, header)

            line_chaves: list[int] = []
            created_articles: list[int] = []
            for lp in plan.lines:
                art_chave, created = self._resolve_entity(
                    session, lp.article, rule.matching.article.table, {})
                if created:
                    created_articles.append(art_chave)
                line_pk = self._next_key(session, rule.lines.table)
                row = {"Chave": line_pk, rule.lines.parent_fk: doc_pk,
                       rule.lines.fields["article"].column: art_chave}
                row.update(lp.columns)
                self._insert(session, rule.lines.table, row)
                line_chaves.append(line_pk)

            return {"document_chave": doc_pk, "supplier_chave": supplier_chave,
                    "line_chaves": line_chaves, "created_supplier": created_supplier,
                    "created_articles": created_articles}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/bills/test_write_executor.py -v`
Expected: PASS (all four tests)

- [ ] **Step 5: Commit**

```bash
git add logic/bills/write_executor.py tests/bills/test_write_executor.py
git commit -m "feat(bills): add multi-table draft-document write executor"
```

---

## Task 8: Audit writer

**Files:**
- Create: `logic/bills/audit_writer.py`
- Test: `tests/bills/test_audit_writer.py`

**Interfaces:**
- Consumes: `logic.chat.audit.AuditLog`, `WritePlan` (Task 2).
- Produces: `class BillAuditWriter` with `__init__(self, audit: AuditLog)` and `record(self, *, operator: str, plan: WritePlan, result: dict, status: str) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_audit_writer.py`:

```python
import json
from logic.chat.audit import AuditLog
from logic.bills.audit_writer import BillAuditWriter
from logic.bills.models import LinePlan, MatchResult, WritePlan


def _plan():
    return WritePlan(proposal_id="p1", supplier=MatchResult(status="matched", chave=7),
                     header={"Total": "123"}, lines=[], rule_doc="purchase_invoice",
                     rule_version=1)


def test_record_writes_one_audit_line(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    writer = BillAuditWriter(log)
    result = {"document_chave": 55, "supplier_chave": 7, "line_chaves": [1, 2],
              "created_supplier": False, "created_articles": []}
    writer.record(operator="alice", plan=_plan(), result=result, status="ok")
    entries = [json.loads(l) for l in (tmp_path / "a.jsonl").read_text().splitlines()]
    assert len(entries) == 1
    e = entries[0]
    assert e["kind"] == "bill_ingest" and e["operator"] == "alice"
    assert e["proposal_id"] == "p1" and e["document_chave"] == 55
    assert e["rule_doc"] == "purchase_invoice" and e["rule_version"] == 1
    assert e["status"] == "ok"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bills/test_audit_writer.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'logic.bills.audit_writer'`

- [ ] **Step 3: Write the audit writer**

Create `logic/bills/audit_writer.py`:

```python
from __future__ import annotations

from logic.chat.audit import AuditLog
from logic.bills.models import WritePlan


class BillAuditWriter:
    def __init__(self, audit: AuditLog) -> None:
        self._audit = audit

    def record(self, *, operator: str, plan: WritePlan, result: dict,
               status: str) -> None:
        self._audit.append({
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
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/bills/test_audit_writer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add logic/bills/audit_writer.py tests/bills/test_audit_writer.py
git commit -m "feat(bills): add bill-ingest audit writer"
```

---

## Task 9: Service orchestration (upload / stage / commit)

**Files:**
- Create: `logic/bills/service.py`
- Test: `tests/bills/test_service.py`

**Interfaces:**
- Consumes: `BillParser` (Task 4), `Matcher` (Task 5), `PendingProposalStore` (Task 6), `BillWriteExecutor` (Task 7), `BillAuditWriter` (Task 8), `arithmetic_warnings`, `Bill`, `BillProposal`, `MatchResult`, `WritePlan`, `LinePlan` (Task 2), `PurchaseInvoiceRule` (Task 1), `pdf_to_text` (Task 3).
- Produces: `class BillService`:
  - `__init__(self, *, anthropic_client, ocr_fn, rule, reader, pending, executor, audit, model, table_prefix="")`
  - `upload(self, pdf_bytes: bytes) -> BillProposal`
  - `stage(self, proposal_id: str, edited: dict) -> dict` — returns `{"ok": True, "write_plan": {...}, "warnings": [...]}` or `{"ok": False, "violations": [...]}`
  - `commit(self, proposal_id: str, operator: str) -> dict` — returns `{"status": "ok", ...result}` or `{"status": "error", "message": ...}`
- Header/line column building maps rule `source` `bill.<attr>` / `line.<attr>` to the rule column; `supplier.match`/`line.match` are resolved by the executor (excluded here).

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_service.py`:

```python
from decimal import Decimal
from pathlib import Path

from logic.bills.models import Bill, BillLine
from logic.bills.pending import PendingProposalStore
from logic.bills.rules.loader import RuleLoader
from logic.bills.service import BillService

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


class FakeParser:
    def __init__(self, bill): self._bill = bill
    def parse(self, pages): return self._bill


class FakeExecutor:
    def __init__(self): self.calls = []
    def execute(self, plan, rule):
        self.calls.append(plan)
        return {"document_chave": 99, "supplier_chave": 7, "line_chaves": [1],
                "created_supplier": False, "created_articles": []}


class FakeAudit:
    def __init__(self): self.records = []
    def record(self, **kw): self.records.append(kw)


def _reader_no_matches(sql, params):
    return []


def _reader_supplier_and_article(sql, params):
    if "Entidades" in sql and params.get("tax_id") == "500100200":
        return [{"Chave": 7, "Nome": "ACME"}]
    if "Artigos" in sql:
        return [{"Chave": 42, "Nome": "Widget"}]
    return []


def _bill():
    return Bill(supplier_name="ACME", supplier_tax_id="500100200",
                number="FT1", issue_date=None, net_total=Decimal("100"),
                vat_total=Decimal("23"), gross_total=Decimal("123"),
                lines=[BillLine(description="Widget", quantity=Decimal("2"),
                                unit_price=Decimal("50"), vat_rate=Decimal("23"),
                                total=Decimal("100"))])


def _service(reader, executor=None, monkeypatch_ocr=None):
    svc = BillService(anthropic_client=None, ocr_fn=lambda b: [],
                      rule=RuleLoader(RULES_DIR).rule(), reader=reader,
                      pending=PendingProposalStore(), executor=executor or FakeExecutor(),
                      audit=FakeAudit(), model="claude-sonnet-4-6")
    svc._parser = FakeParser(_bill())  # inject parser (constructor builds a real one)
    return svc


def test_upload_produces_matched_proposal():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    assert proposal.supplier_match.status == "matched"
    assert proposal.line_matches[0].status == "matched"
    assert svc._pending.get(proposal.proposal_id) is not None


def test_upload_flags_new_supplier_and_article():
    svc = _service(_reader_no_matches)
    proposal = svc.upload(b"%PDF")
    assert proposal.supplier_match.status == "new"
    assert proposal.line_matches[0].status == "new"


def test_stage_rejects_unconfirmed_new_records():
    svc = _service(_reader_no_matches)
    proposal = svc.upload(b"%PDF")
    result = svc.stage(proposal.proposal_id, proposal.model_dump(mode="json"))
    assert result["ok"] is False
    assert any("confirm" in v["message"].lower() for v in result["violations"])


def test_stage_rejects_missing_required_total():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    edited = proposal.model_dump(mode="json")
    edited["bill"]["gross_total"] = None
    result = svc.stage(proposal.proposal_id, edited)
    assert result["ok"] is False
    assert any("total" in v["message"].lower() for v in result["violations"])


def test_stage_then_commit_writes_and_audits():
    executor = FakeExecutor()
    svc = _service(_reader_supplier_and_article, executor=executor)
    proposal = svc.upload(b"%PDF")
    staged = svc.stage(proposal.proposal_id, proposal.model_dump(mode="json"))
    assert staged["ok"] is True
    out = svc.commit(proposal.proposal_id, operator="alice")
    assert out["status"] == "ok" and out["document_chave"] == 99
    assert len(executor.calls) == 1
    assert svc._audit.records[0]["status"] == "ok"
    # proposal consumed
    assert svc.commit(proposal.proposal_id, operator="alice")["status"] == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/bills/test_service.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'logic.bills.service'`

- [ ] **Step 3: Write the service**

Create `logic/bills/service.py`:

```python
from __future__ import annotations
import uuid
from typing import Any, Callable

from logic.bills.extract.parser import BillParser
from logic.bills.matching import Matcher
from logic.bills.models import (Bill, BillLine, BillProposal, LinePlan,
                                MatchResult, WritePlan, arithmetic_warnings)
from logic.bills.pending import PendingProposalStore
from logic.bills.rules.models import PurchaseInvoiceRule


class BillService:
    def __init__(self, *, anthropic_client: Any, ocr_fn: Callable[[bytes], list],
                 rule: PurchaseInvoiceRule, reader: Callable, pending: PendingProposalStore,
                 executor, audit, model: str, table_prefix: str = "") -> None:
        self._ocr = ocr_fn
        self._rule = rule
        self._reader = reader
        self._pending = pending
        self._executor = executor
        self._audit = audit
        self._prefix = table_prefix
        self._parser = BillParser(anthropic_client, model, rule)
        self._matcher = Matcher(reader, rule, table_prefix=table_prefix)

    # ---- upload -----------------------------------------------------------
    def upload(self, pdf_bytes: bytes) -> BillProposal:
        pages = self._ocr(pdf_bytes)
        bill = self._parser.parse(pages)
        supplier_match = self._matcher.match_supplier(bill)
        line_matches = [self._matcher.match_line(ln) for ln in bill.lines]
        proposal = BillProposal(
            proposal_id="bill_" + uuid.uuid4().hex[:12], bill=bill,
            supplier_match=supplier_match, line_matches=line_matches,
            warnings=arithmetic_warnings(bill))
        self._pending.put(proposal.proposal_id, proposal)
        return proposal

    # ---- stage ------------------------------------------------------------
    def _bill_value(self, bill: Bill, source: str):
        # getattr default keeps mapped-but-unextracted fields (e.g. notes) safe.
        return getattr(bill, source.split(".", 1)[1], None)

    def _line_value(self, line: BillLine, source: str):
        return getattr(line, source.split(".", 1)[1], None)

    def _build_header(self, bill: Bill) -> tuple[dict, list[dict]]:
        cols, violations = {}, []
        for name, fr in self._rule.header.fields.items():
            if fr.source in ("supplier.match",):
                continue  # resolved by executor
            val = self._bill_value(bill, fr.source)
            if fr.required and (val is None or val == ""):
                violations.append({"field": name, "message": f"{name} is required"})
                continue
            if val is not None:
                cols[fr.column] = str(val)
        return cols, violations

    def _build_line(self, line: BillLine) -> tuple[dict, list[dict]]:
        cols, violations = {}, []
        for name, fr in self._rule.lines.fields.items():
            if fr.source == "line.match":
                continue
            val = self._line_value(line, fr.source)
            if fr.required and (val is None or val == ""):
                violations.append({"field": name, "message": f"line {name} is required"})
                continue
            if val is not None:
                cols[fr.column] = str(val)
        return cols, violations

    def stage(self, proposal_id: str, edited: dict) -> dict:
        proposal = BillProposal.model_validate(edited)
        self._pending.put(proposal_id, proposal)  # keep latest edits
        violations: list[dict] = []

        # confirmation gate for new records
        if proposal.supplier_match.status == "new" and not proposal.supplier_match.confirmed:
            violations.append({"field": "supplier",
                               "message": "new supplier must be confirmed before writing"})
        for i, lm in enumerate(proposal.line_matches):
            if lm.status == "new" and not lm.confirmed:
                violations.append({"field": f"line[{i}]",
                                   "message": "new article must be confirmed before writing"})
            if lm.status == "ambiguous" and lm.chave is None:
                violations.append({"field": f"line[{i}]",
                                   "message": "pick a candidate article before writing"})
        if proposal.supplier_match.status == "ambiguous" and proposal.supplier_match.chave is None:
            violations.append({"field": "supplier",
                               "message": "pick a candidate supplier before writing"})

        header, hv = self._build_header(proposal.bill)
        violations += hv
        line_plans: list[LinePlan] = []
        for i, (line, lm) in enumerate(zip(proposal.bill.lines, proposal.line_matches)):
            cols, lv = self._build_line(line)
            violations += lv
            line_plans.append(LinePlan(article=lm, columns=cols))

        if violations:
            return {"ok": False, "violations": violations}

        plan = WritePlan(proposal_id=proposal_id, supplier=proposal.supplier_match,
                         header=header, lines=line_plans,
                         rule_doc=self._rule.document, rule_version=self._rule.version)
        self._pending.put(proposal_id + ":plan", plan)
        return {"ok": True, "write_plan": plan.model_dump(mode="json"),
                "warnings": self._duplicate_warnings(proposal.bill) + proposal.warnings}

    def _duplicate_warnings(self, bill: Bill) -> list[str]:
        if not bill.number:
            return []
        rows = self._reader(
            f"SELECT Chave FROM {self._prefix}{self._rule.header.table} WHERE VRef = :v",
            {"v": bill.number})
        return [f"a document with supplier ref {bill.number} already exists"] if rows else []

    # ---- commit -----------------------------------------------------------
    def commit(self, proposal_id: str, operator: str) -> dict:
        plan = self._pending.pop(proposal_id + ":plan")
        if plan is None:
            return {"status": "error", "message": "no staged plan; stage first"}
        try:
            result = self._executor.execute(plan, self._rule)
            self._audit.record(operator=operator, plan=plan, result=result, status="ok")
            self._pending.pop(proposal_id)
            return {"status": "ok", **result}
        except Exception as e:  # noqa: BLE001
            self._audit.record(operator=operator, plan=plan,
                               result={}, status="error")
            return {"status": "error", "message": str(e)[:500]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/bills/test_service.py -v`
Expected: PASS (all six tests)

- [ ] **Step 5: Commit**

```bash
git add logic/bills/service.py tests/bills/test_service.py
git commit -m "feat(bills): add BillService orchestration (upload/stage/commit)"
```

---

## Task 10: Write connection + FastAPI app

**Files:**
- Create: `db/bills_connection.py`
- Create: `logic/bills/app.py`
- Test: `tests/bills/test_connection.py`, `tests/bills/test_app.py`

**Interfaces:**
- Consumes: `BillService` (Task 9), all wiring pieces.
- Produces: `db.bills_connection.get_bills_write_session()` (contextmanager, commits/rolls-back/closes, reads `BILLS_WRITE_DATABASE_URL`).
- Produces: FastAPI `app` with `POST /bills/upload` (multipart `file`), `POST /bills/stage/{proposal_id}`, `POST /bills/commit/{proposal_id}`, an operator cookie endpoint `POST /bills/operator`, and static UI at `/`.

- [ ] **Step 1: Write the failing connection test**

Create `tests/bills/test_connection.py`:

```python
import pytest
import db.bills_connection as bc


def test_missing_env_raises(monkeypatch):
    monkeypatch.delenv("BILLS_WRITE_DATABASE_URL", raising=False)
    bc._engine = None
    bc._SessionLocal = None
    with pytest.raises(RuntimeError, match="BILLS_WRITE_DATABASE_URL"):
        with bc.get_bills_write_session():
            pass
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/bills/test_connection.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'db.bills_connection'`

- [ ] **Step 3: Write the connection**

Create `db/bills_connection.py` (mirror `db/devcare_connection.py`):

```python
from __future__ import annotations
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine = None
_SessionLocal = None


def _factory():
    global _engine, _SessionLocal
    if _engine is None:
        url = os.environ.get("BILLS_WRITE_DATABASE_URL")
        if not url:
            raise RuntimeError("BILLS_WRITE_DATABASE_URL is not set")
        _engine = create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=5)
        _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    return _SessionLocal


@contextmanager
def get_bills_write_session() -> Generator[Session, None, None]:
    """Yields a session; commits on success, rolls back and re-raises on error, always closes."""
    session = _factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

- [ ] **Step 4: Run connection test to verify it passes**

Run: `pytest tests/bills/test_connection.py -v`
Expected: PASS

- [ ] **Step 5: Write the failing app test**

Create `tests/bills/test_app.py`:

```python
from decimal import Decimal
from fastapi.testclient import TestClient

import logic.bills.app as appmod
from logic.bills.models import Bill, BillLine, BillProposal, MatchResult


class StubService:
    def __init__(self):
        self._proposal = BillProposal(
            proposal_id="bill_x", bill=Bill(supplier_name="ACME"),
            supplier_match=MatchResult(status="matched", chave=7),
            line_matches=[], warnings=[])
    def upload(self, pdf_bytes):
        return self._proposal
    def stage(self, proposal_id, edited):
        return {"ok": True, "write_plan": {"proposal_id": proposal_id}, "warnings": []}
    def commit(self, proposal_id, operator):
        return {"status": "ok", "document_chave": 99}


def _client(monkeypatch):
    monkeypatch.setattr(appmod, "get_service", lambda: StubService())
    return TestClient(appmod.app)


def test_upload_returns_proposal(monkeypatch):
    client = _client(monkeypatch)
    client.post("/bills/operator", json={"name": "alice"})
    r = client.post("/bills/upload", files={"file": ("b.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 200
    assert r.json()["proposal_id"] == "bill_x"


def test_commit_requires_operator(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/bills/commit/bill_x", json={})
    assert r.status_code == 400


def test_stage_then_commit(monkeypatch):
    client = _client(monkeypatch)
    client.post("/bills/operator", json={"name": "alice"})
    assert client.post("/bills/stage/bill_x", json={"proposal_id": "bill_x"}).json()["ok"] is True
    assert client.post("/bills/commit/bill_x", json={}).json()["document_chave"] == 99
```

- [ ] **Step 6: Run it to verify it fails**

Run: `pytest tests/bills/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'logic.bills.app'`

- [ ] **Step 7: Write the app**

Create `logic/bills/app.py` (mirror `logic/devcare/app.py` wiring; UI-serving block copied verbatim, adjusting paths/asset names):

```python
from __future__ import annotations
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from dotenv import load_dotenv

from db.connection import get_session as _read_session
from db.bills_connection import get_bills_write_session
from logic.chat.audit import AuditLog
from logic.bills.audit_writer import BillAuditWriter
from logic.bills.extract.ocr import pdf_to_text
from logic.bills.pending import PendingProposalStore
from logic.bills.rules.loader import RuleLoader
from logic.bills.service import BillService
from logic.bills.write_executor import BillWriteExecutor

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")

_RULES_DIR = _REPO_ROOT / "business_rules" / "bills"
_WRITE_LOG_PATH = Path(os.environ.get(
    "BILLS_WRITE_LOG_PATH", str(_REPO_ROOT / "logs" / "bills_writes.jsonl")))
_UI_DIR = _REPO_ROOT / "ui" / "bills"
_OPERATOR_COOKIE = "bills_operator"
_TABLE_PREFIX = os.environ.get("BILLS_TABLE_PREFIX", "ForumSI.dbo.")

app = FastAPI(title="Bill Ingestion")

_service: BillService | None = None
_pending = PendingProposalStore()


def _read(sql: str, params: dict) -> list[dict]:
    with _read_session() as s:
        result = s.execute(text(sql), params or {})
        cols = list(result.keys())
        return [dict(zip(cols, row)) for row in result.fetchall()]


def _build_anthropic():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def get_service() -> BillService:
    global _service
    if _service is None:
        rule = RuleLoader(_RULES_DIR).rule()
        _service = BillService(
            anthropic_client=_build_anthropic(), ocr_fn=pdf_to_text, rule=rule,
            reader=_read, pending=_pending,
            executor=BillWriteExecutor(get_bills_write_session, table_prefix=_TABLE_PREFIX),
            audit=BillAuditWriter(AuditLog(_WRITE_LOG_PATH)),
            model="claude-sonnet-4-6", table_prefix=_TABLE_PREFIX)
    return _service


def _operator(request: Request) -> str | None:
    return request.cookies.get(_OPERATOR_COOKIE)


@app.post("/bills/operator")
def set_operator(response: Response, body: dict) -> dict:
    name = (body or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    response.set_cookie(_OPERATOR_COOKIE, name, httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return {"operator": name}


@app.post("/bills/upload")
async def upload(request: Request, file: UploadFile = File(...)) -> Response:
    if not _operator(request):
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    pdf_bytes = await file.read()
    try:
        proposal = get_service().upload(pdf_bytes)
    except RuntimeError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    return JSONResponse(proposal.model_dump(mode="json"))


@app.post("/bills/stage/{proposal_id}")
async def stage(proposal_id: str, request: Request) -> Response:
    if not _operator(request):
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    edited = await request.json()
    try:
        return JSONResponse(get_service().stage(proposal_id, edited))
    except RuntimeError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)


@app.post("/bills/commit/{proposal_id}")
def commit(proposal_id: str, request: Request) -> Response:
    operator = _operator(request)
    if not operator:
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    try:
        return JSONResponse(get_service().commit(proposal_id, operator))
    except RuntimeError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)


@app.get("/favicon.ico", include_in_schema=False)
def _favicon() -> Response:
    return Response(status_code=204)


if _UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
```

- [ ] **Step 8: Run the app tests to verify they pass**

Run: `pytest tests/bills/test_app.py -v`
Expected: PASS (all three). Note: `TestClient` needs `httpx`, already a dev dependency.

- [ ] **Step 9: Commit**

```bash
git add db/bills_connection.py logic/bills/app.py tests/bills/test_connection.py tests/bills/test_app.py
git commit -m "feat(bills): add write connection and FastAPI endpoints"
```

---

## Task 11: Review-form UI

**Files:**
- Create: `ui/bills/index.html`, `ui/bills/app.js`, `ui/bills/bills.css`
- Verify: manual (documented below); the UI mounts under Task 10's app.

**Interfaces:**
- Consumes the three endpoints from Task 10 and renders the `BillProposal` JSON shape from Task 2.

- [ ] **Step 1: Write `ui/bills/index.html`**

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Bill Ingestion</title>
  <link rel="stylesheet" href="/bills.css" />
</head>
<body>
  <header>
    <h1>Bill Ingestion</h1>
    <label>Operator <input id="operator" placeholder="your name" /></label>
  </header>
  <main>
    <section id="upload-zone">
      <input type="file" id="file" accept="application/pdf" />
      <button id="upload-btn">Upload &amp; extract</button>
      <span id="status"></span>
    </section>
    <form id="review" hidden></form>
  </main>
  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `ui/bills/bills.css`**

```css
* { box-sizing: border-box; }
body { font-family: system-ui, sans-serif; margin: 0; color: #1a1a1a; }
header { display: flex; justify-content: space-between; align-items: center;
  padding: 12px 20px; border-bottom: 1px solid #ddd; }
main { padding: 20px; max-width: 900px; margin: 0 auto; }
#upload-zone { display: flex; gap: 8px; align-items: center; margin-bottom: 20px; }
table { width: 100%; border-collapse: collapse; margin: 12px 0; }
th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 14px; }
input.cell { width: 100%; border: none; }
.badge { padding: 2px 6px; border-radius: 4px; font-size: 12px; }
.matched { background: #e6f4ea; } .ambiguous { background: #fef7e0; } .new { background: #e8f0fe; }
.warn { color: #b06000; }
button { padding: 6px 12px; cursor: pointer; }
#accept { background: #1a73e8; color: #fff; border: none; border-radius: 4px; padding: 10px 16px; }
select.cell { width: 100%; }
```

- [ ] **Step 3: Write `ui/bills/app.js`**

```javascript
const $ = (s) => document.querySelector(s);
let proposal = null;

async function setOperator() {
  const name = $("#operator").value.trim();
  if (name) await fetch("/bills/operator", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }) });
}

async function upload() {
  await setOperator();
  const file = $("#file").files[0];
  if (!file) { $("#status").textContent = "pick a PDF first"; return; }
  $("#status").textContent = "extracting…";
  const fd = new FormData(); fd.append("file", file);
  const res = await fetch("/bills/upload", { method: "POST", body: fd });
  const data = await res.json();
  if (!res.ok) { $("#status").textContent = data.detail || "upload failed"; return; }
  proposal = data; $("#status").textContent = ""; render();
}

function badge(status) { return `<span class="badge ${status}">${status}</span>`; }

function candidateSelect(cands, attr) {
  const opts = cands.map((c) => `<option value="${c.chave}">${c.label}</option>`).join("");
  return `<select class="cell" ${attr}><option value="">— pick —</option>${opts}</select>`;
}

function matchCell(m, i) {
  if (m.status === "new")
    return `${badge(m.status)} <label><input type="checkbox" data-confirm-line="${i}"> create</label>`;
  if (m.status === "ambiguous")
    return `${badge(m.status)} ${candidateSelect(m.candidates, `data-pick-line="${i}"`)}`;
  return badge(m.status);
}

function render() {
  const b = proposal.bill;
  const rows = b.lines.map((ln, i) => {
    const m = proposal.line_matches[i];
    return `<tr>
      <td><input class="cell" data-line="${i}" data-k="description" value="${ln.description ?? ""}"></td>
      <td><input class="cell" data-line="${i}" data-k="quantity" value="${ln.quantity ?? ""}"></td>
      <td><input class="cell" data-line="${i}" data-k="unit_price" value="${ln.unit_price ?? ""}"></td>
      <td><input class="cell" data-line="${i}" data-k="vat_rate" value="${ln.vat_rate ?? ""}"></td>
      <td><input class="cell" data-line="${i}" data-k="total" value="${ln.total ?? ""}"></td>
      <td>${matchCell(m, i)}</td>
    </tr>`;
  }).join("");
  const warnings = (proposal.warnings || []).map((w) => `<li class="warn">${w}</li>`).join("");
  $("#review").innerHTML = `
    <h2>Supplier ${badge(proposal.supplier_match.status)}</h2>
    <p><input class="cell" data-h="supplier_name" value="${b.supplier_name ?? ""}"> ·
       NIF <input class="cell" data-h="supplier_tax_id" value="${b.supplier_tax_id ?? ""}"></p>
    ${proposal.supplier_match.status === "new" ?
      `<label><input type="checkbox" id="confirm-supplier"> create this supplier</label>` :
      proposal.supplier_match.status === "ambiguous" ?
      candidateSelect(proposal.supplier_match.candidates, `id="pick-supplier"`) : ""}
    <p>Invoice # <input class="cell" data-h="number" value="${b.number ?? ""}"> ·
       Date <input class="cell" data-h="issue_date" value="${b.issue_date ?? ""}"> ·
       Total <input class="cell" data-h="gross_total" value="${b.gross_total ?? ""}"></p>
    <table><thead><tr><th>Description</th><th>Qty</th><th>Unit</th><th>VAT</th><th>Total</th><th>Match</th></tr></thead>
      <tbody>${rows}</tbody></table>
    <ul>${warnings}</ul>
    <button id="accept" type="button">Accept &amp; write draft</button>
    <p id="result"></p>`;
  $("#review").hidden = false;
  $("#accept").addEventListener("click", accept);
}

function collectEdits() {
  const b = proposal.bill;
  document.querySelectorAll("[data-h]").forEach((el) => { b[el.dataset.h] = el.value || null; });
  document.querySelectorAll("[data-line]").forEach((el) => {
    b.lines[+el.dataset.line][el.dataset.k] = el.value || null; });
  const cs = document.querySelector("#confirm-supplier");
  if (cs) proposal.supplier_match.confirmed = cs.checked;
  document.querySelectorAll("[data-confirm-line]").forEach((el) => {
    proposal.line_matches[+el.dataset.confirmLine].confirmed = el.checked; });
  const ps = document.querySelector("#pick-supplier");
  if (ps && ps.value) {
    proposal.supplier_match.chave = +ps.value;
    proposal.supplier_match.status = "matched";
  }
  document.querySelectorAll("[data-pick-line]").forEach((el) => {
    if (el.value) {
      const m = proposal.line_matches[+el.dataset.pickLine];
      m.chave = +el.value; m.status = "matched";
    }
  });
}

async function accept() {
  collectEdits();
  const id = proposal.proposal_id;
  const staged = await (await fetch(`/bills/stage/${id}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(proposal) })).json();
  if (!staged.ok) {
    $("#result").innerHTML = staged.violations.map((v) =>
      `<span class="warn">${v.field}: ${v.message}</span>`).join("<br>");
    return;
  }
  const out = await (await fetch(`/bills/commit/${id}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
  $("#result").textContent = out.status === "ok"
    ? `Draft document created: Chave ${out.document_chave}`
    : `Error: ${out.message}`;
}

$("#upload-btn").addEventListener("click", upload);
```

- [ ] **Step 4: Manual verification**

Start the server and drive the happy path (requires `.env` with `ANTHROPIC_API_KEY`, `DATABASE_URL`, `BILLS_WRITE_DATABASE_URL`, plus Tesseract + Poppler installed):

```bash
uvicorn logic.bills.app:app --reload --port 8002
```

Open http://localhost:8002/, set operator, upload a sample supplier invoice PDF, confirm the review form shows supplier + line-item table with match badges, tick any "create" boxes, click Accept, and verify it reports a created draft Chave. Then confirm one audit line was appended:

```bash
tail -n 1 logs/bills_writes.jsonl
```

Expected: a JSON line with `"kind":"bill_ingest"`, `"status":"ok"`, and the `document_chave`.

- [ ] **Step 5: Commit**

```bash
git add ui/bills/
git commit -m "feat(bills): add upload + review-form UI"
```

---

## Task 12: Documentation

**Files:**
- Modify: `CLAUDE.md` (Active domains table + run instructions)

**Interfaces:** none.

- [ ] **Step 1: Update the Active domains table**

In `CLAUDE.md`, add a row under **Active domains**:

```
| Bill ingestion | [business_rules/bills/](business_rules/bills/) (purchase_invoice) | Active (draft writes) |
```

- [ ] **Step 2: Add run instructions**

After the DevCare run line in `CLAUDE.md`, add:

```
Run the Bill ingestion server: `uvicorn logic.bills.app:app --reload --port 8002`, then open http://localhost:8002/.
Bill ingestion requires `ANTHROPIC_API_KEY`, `DATABASE_URL` (read-only, for lookups), `BILLS_WRITE_DATABASE_URL` (a writable login scoped to the ForumSI mirror), and the Tesseract + Poppler binaries (`tesseract-ocr`, `poppler-utils`). Accepted bills are written as draft, uncertified `Doc001` documents.
```

- [ ] **Step 3: Run the full bills suite**

Run: `pytest tests/bills/ -v`
Expected: PASS (all modules).

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(bills): document bill ingestion domain and run instructions"
```

---

## Self-Review Notes (verify during execution)

- **Spec coverage:** enterprise doc (T1), extraction OCR+parse (T3, T4), matching (T5), proposal→stage→commit lifecycle (T6, T9), atomic multi-table write with draft defaults (T7), audit (T8), standalone UI (T11), error handling (OcrUnavailable T3, config errors T10, arithmetic warnings T2/T9, duplicate warning T9, rollback T7), tests per component (every task). Open items resolved in T0.
- **Numbering caveat honored:** the executor never reads/writes `Numeradores`; `Codigo` is left unset on the draft header.
- **Type consistency:** `MatchResult.confirmed`, `WritePlan`/`LinePlan`, `document_chave`/`supplier_chave`/`created_articles` names are identical across T2, T7, T8, T9.
```
