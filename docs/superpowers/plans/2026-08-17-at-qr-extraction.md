# AT QR Code Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decode the Portuguese tax-authority QR code on supplier invoices and use its fields in preference to what the vision model reads off the page.

**Architecture:** `decode()` turns original image bytes into a payload string; `parse()` turns that string into an `AtQr`; `merge()` folds the `AtQr` into the vision-extracted `Bill` and returns warnings. Only `decode()` touches an image library, so the entire field-semantics and merge policy is testable with no binary dependency.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, plus one QR decoding library chosen empirically in Task 1.

**Spec:** [docs/superpowers/specs/2026-08-17-at-qr-extraction-design.md](../specs/2026-08-17-at-qr-extraction-design.md)

## Global Constraints

- **The QR can only ever improve the result.** No QR condition — missing, undecodable, non-AT, malformed, or decoder library not installed — may cause an ingestion that would otherwise have succeeded to fail. `decode()` returns `None` instead of raising, always.
- `decode()` runs on the **original** upload bytes, never on `prepare()`'s output. `prepare()` downscales to a 1568px long edge and the QR is already near the decodable limit at source resolution.
- An AT payload is `KEY:VALUE` pairs joined by `*`. A payload is only treated as an AT invoice code if it carries at least `A` and `O`.
- Unknown fields are ignored, never an error — the format permits fields this code does not consume.
- `logic/bills/extract/at_qr.py` imports nothing beyond the standard library and Pydantic. No image library, no decoder.
- Field meanings (Portaria 195/2020): `A` issuer NIF, `B` buyer NIF, `D` doc type, `E` doc status, `F` date `YYYYMMDD`, `G` document number, `N` total tax, `O` total with tax, `I2/I3/I5/I7` mainland taxable bases, `J*`/`K*` Açores/Madeira equivalents, `L` non-subject amount.
- The existing `supplier_tax_id` NIF check-digit guard stays in force after the merge — it is not bypassed for QR-sourced values.
- Tests offline and deterministic. Tests needing `bills_examples/` **skip** when it is absent (it is untracked in git), never fail.
- Interpreter: `C:/Users/joaog/erp_venv/Scripts/python.exe` — the repo's `.venv` is corrupted by OneDrive sync.
- Baseline before this work: `tests/bills/` is 116 passing with two expected warnings (a Starlette deprecation and a deliberate `DecompressionBombWarning`).

## File Structure

| File | Responsibility |
|---|---|
| `logic/bills/extract/at_qr.py` (create) | `AtQr` model, `parse()`, `merge()` — pure, no image deps |
| `logic/bills/extract/qr.py` (create) | `decode()` — the only file that touches a decoder library |
| `logic/bills/service.py` (modify) | Calls decode → parse → merge in `_extract`; passes warnings to `upload` |
| `pyproject.toml` (modify) | The one new dependency, chosen in Task 1 |
| `tests/bills/test_at_qr.py` (create) | Parsing and merge policy — always runs |
| `tests/bills/test_qr.py` (create) | Real-image decoding — skips without fixtures or decoder |
| `tests/bills/test_service.py` (modify) | Wiring: QR overrides vision, absence changes nothing |

## Test vectors used throughout

These payloads are constructed from field values **verified against the real invoices** in the
previous cycle's Task 8 report — they are realistic reconstructions, not strings decoded from
the images (nothing has been decoded yet).

`SAGE` — `scanner_forumsi_1.jpeg`, whose supplier NIF the vision model misread as `502267583`:

```
A:502667583*B:514380802*C:PT*D:FT*E:N*F:20260805*G:FCL FCL-P26/029346*H:J6FHJGSV-029346*I1:PT*I7:2058.72*I8:473.51*N:473.51*O:2532.23*Q:J6YV*R:213
```

`VODAFONE` — `scanner_forumsi_2.jpeg`:

```
A:502544180*B:514380802*C:PT*D:FT*E:N*F:20260611*G:FT 101/115536773*H:JFHT-115536773*I1:PT*I7:108.40*I8:24.93*N:24.93*O:133.33*Q:A1B2*R:1234
```

Both reconcile: 2058.72 + 473.51 = 2532.23, and 108.40 + 24.93 = 133.33.

---

### Task 1: Decoder spike — choose the dependency by evidence

**Throwaway. No production code, no commit of code.** Its only output is a decision and a
report. If nothing decodes, we stop and reconsider rather than building unused machinery.

**Why this is first:** the examples are 1080×1920 and the QR on `scanner_forumsi_1` occupies
roughly 120×120 px. An AT payload of ~150–200 characters implies ~49–61 modules per side —
about two pixels per module before JPEG artefacts. Whether that decodes at all is an open
empirical question.

**Files:**
- Create (scratchpad, not committed): `<scratchpad>/qr_spike.py`

- [ ] **Step 1: Install both candidates into the venv**

```bash
C:/Users/joaog/erp_venv/Scripts/python.exe -m pip install opencv-python-headless pyzbar
```

Note in your report whether `pyzbar` imports successfully — on Windows its wheel bundles the
zbar DLLs, but if the import fails with a `libzbar` error, record that as a finding, since it
directly affects the deployment cost of choosing it.

- [ ] **Step 2: Write the spike**

For each of the six `bills_examples/*.jpeg`, apply EXIF rotation, then try to decode with
**every combination** of:

- Decoder: OpenCV `cv2.QRCodeDetector().detectAndDecode()`, OpenCV `detectAndDecodeMulti()`, and `pyzbar.pyzbar.decode()`
- Image variant: full resolution as-is; grayscale; grayscale upscaled 2×; grayscale upscaled 4× (`cv2.INTER_CUBIC`); and Otsu-thresholded grayscale

Print one line per (file, decoder, variant): decoded / not decoded, and when decoded, the
first 80 characters of the payload.

- [ ] **Step 3: Run it**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe <scratchpad>/qr_spike.py`

- [ ] **Step 4: Report the decision**

Report a matrix of file × decoder × variant. Then state plainly:

1. Which decoder decoded the most invoices, and how many of the five QR-bearing files
   (all but `scanner_forumsi_4.jpeg`, which has no QR).
2. Which image variant was needed — this determines what `decode()` must do internally.
3. Whether any decoded payload actually starts with `A:` and contains `*O:`, confirming these
   are AT codes and not some other QR.
4. Your recommended dependency, with reasoning. Weight `opencv-python-headless` favourably if
   results are close: it is a pure pip wheel, whereas `pyzbar` needs `libzbar0` from apt on
   the Render deployment, and this project has already been bitten repeatedly by system
   binaries (Tesseract, Poppler).

**STOP after this task and report to the controller before Task 2 begins.** If zero files
decode under any combination, the remaining tasks are not worth building.

---

### Task 2: Parse an AT payload

**Files:**
- Create: `logic/bills/extract/at_qr.py`
- Test: `tests/bills/test_at_qr.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `class AtQr(BaseModel)` with fields `supplier_tax_id: str | None`, `buyer_tax_id: str | None`, `doc_type: str | None`, `status: str | None`, `issue_date: date | None`, `number: str | None`, `net_total: Decimal | None`, `vat_total: Decimal | None`, `gross_total: Decimal | None`; and `parse(payload: str) -> AtQr | None`. Task 3 consumes both.

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_at_qr.py`:

```python
from datetime import date
from decimal import Decimal

import pytest

from logic.bills.extract.at_qr import parse

SAGE = ("A:502667583*B:514380802*C:PT*D:FT*E:N*F:20260805*"
        "G:FCL FCL-P26/029346*H:J6FHJGSV-029346*I1:PT*I7:2058.72*I8:473.51*"
        "N:473.51*O:2532.23*Q:J6YV*R:213")


def test_parse_separates_issuer_from_buyer():
    # The whole point of the feature: A is the supplier, B is the buyer, and no
    # layout or label heuristic is involved.
    qr = parse(SAGE)
    assert qr.supplier_tax_id == "502667583"
    assert qr.buyer_tax_id == "514380802"


def test_parse_reads_header_fields():
    qr = parse(SAGE)
    assert qr.number == "FCL FCL-P26/029346"
    assert qr.issue_date == date(2026, 8, 5)
    assert qr.doc_type == "FT"
    assert qr.status == "N"


def test_parse_reads_totals():
    qr = parse(SAGE)
    assert qr.gross_total == Decimal("2532.23")
    assert qr.vat_total == Decimal("473.51")
    # net comes from the taxable bases, here the single normal-rate base I7
    assert qr.net_total == Decimal("2058.72")


def test_parse_sums_multiple_taxable_bases():
    payload = ("A:502667583*B:514380802*D:FT*E:N*F:20260805*G:FT 1/1*"
               "I3:100.00*I4:6.00*I7:200.00*I8:46.00*L:10.00*"
               "N:52.00*O:362.00")
    assert parse(payload).net_total == Decimal("310.00")  # 100 + 200 + 10


def test_parse_falls_back_to_gross_minus_vat_when_no_bases_present():
    payload = "A:502667583*D:FT*E:N*F:20260805*G:FT 1/1*N:23.00*O:123.00"
    assert parse(payload).net_total == Decimal("100.00")


def test_parse_ignores_unknown_fields():
    # The format permits fields we do not consume; they must not break decoding.
    payload = SAGE + "*Z9:something-new*ZZ:more"
    assert parse(payload).supplier_tax_id == "502667583"


@pytest.mark.parametrize("payload", [
    "",
    "just some text",
    "https://example.com/not-an-invoice",
    "A:502667583",          # has A but no O
    "O:123.00",             # has O but no A
])
def test_parse_rejects_non_at_payloads(payload):
    assert parse(payload) is None


def test_parse_survives_malformed_pairs():
    # A stray token with no colon must not raise.
    payload = "A:502667583*garbage*O:123.00*N:23.00*F:20260805"
    qr = parse(payload)
    assert qr is not None and qr.supplier_tax_id == "502667583"


def test_parse_returns_none_for_an_unparseable_date_but_keeps_the_rest():
    payload = "A:502667583*O:123.00*N:23.00*F:notadate*G:FT 1/1"
    qr = parse(payload)
    assert qr is not None
    assert qr.issue_date is None
    assert qr.number == "FT 1/1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_at_qr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.bills.extract.at_qr'`

- [ ] **Step 3: Write minimal implementation**

Create `logic/bills/extract/at_qr.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel

# Portaria 195/2020 field keys. Bases are the taxable amounts per rate; the
# mainland (I), Açores (J) and Madeira (K) blocks share the same layout.
_BASE_KEYS = tuple(f"{region}{n}" for region in "IJK" for n in (2, 3, 5, 7)) + ("L",)


class AtQr(BaseModel):
    supplier_tax_id: str | None = None
    buyer_tax_id: str | None = None
    doc_type: str | None = None
    status: str | None = None
    issue_date: date | None = None
    number: str | None = None
    net_total: Decimal | None = None
    vat_total: Decimal | None = None
    gross_total: Decimal | None = None


def _fields(payload: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in payload.split("*"):
        key, sep, value = token.partition(":")
        if sep:  # tokens without a colon are skipped, not an error
            out[key.strip()] = value.strip()
    return out


def _decimal(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def _net(fields: dict[str, str], vat: Decimal | None,
         gross: Decimal | None) -> Decimal | None:
    bases = [d for k in _BASE_KEYS if (d := _decimal(fields.get(k))) is not None]
    if bases:
        return sum(bases, Decimal("0"))
    if gross is not None and vat is not None:
        return gross - vat
    return None


def parse(payload: str) -> AtQr | None:
    """Read a Portuguese AT invoice QR payload.

    Returns None for anything that is not one. A and O together are what
    distinguish an AT invoice code from any other QR that might be on the page —
    a URL, a payment code, a logo watermark.

    Unlike the vision model, this cannot misread a digit: the payload is emitted
    by certified invoicing software, so where it and the model disagree, it wins.
    """
    if not payload:
        return None
    fields = _fields(payload)
    if "A" not in fields or "O" not in fields:
        return None

    vat = _decimal(fields.get("N"))
    gross = _decimal(fields.get("O"))
    try:
        issued = datetime.strptime(fields["F"], "%Y%m%d").date() if "F" in fields else None
    except ValueError:
        issued = None

    return AtQr(
        supplier_tax_id=fields.get("A") or None,
        buyer_tax_id=fields.get("B") or None,
        doc_type=fields.get("D") or None,
        status=fields.get("E") or None,
        issue_date=issued,
        number=fields.get("G") or None,
        net_total=_net(fields, vat, gross),
        vat_total=vat,
        gross_total=gross,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_at_qr.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add logic/bills/extract/at_qr.py tests/bills/test_at_qr.py
git commit -m "feat(bills): parse Portuguese AT invoice QR payloads"
```

---

### Task 3: Merge QR fields into the vision-extracted bill

**Files:**
- Modify: `logic/bills/extract/at_qr.py` (append `merge`)
- Test: `tests/bills/test_at_qr.py` (append)

**Interfaces:**
- Consumes: `AtQr` and `parse` from Task 2; `Bill` from `logic.bills.models`.
- Produces: `merge(bill: Bill, qr: AtQr) -> tuple[Bill, list[str]]` returning the amended bill and warnings. Task 5 calls it.

- [ ] **Step 1: Write the failing test**

Append to `tests/bills/test_at_qr.py`:

```python
from logic.bills.extract.at_qr import merge
from logic.bills.models import Bill, BillLine


def _vision_bill(**over) -> Bill:
    base = dict(supplier_name="SAGE PORTUGAL", supplier_tax_id="502267583",
                buyer_tax_id="514380802", number="FCL FCL-P26/029346",
                issue_date=date(2026, 8, 5), net_total=Decimal("2058.72"),
                vat_total=Decimal("473.51"), gross_total=Decimal("2532.23"),
                lines=[BillLine(description="SubA Accountants", total=Decimal("1998.62"))])
    base.update(over)
    return Bill(**base)


def test_merge_overwrites_the_misread_supplier_nif():
    # This is the real defect from the previous cycle: vision read 502267583
    # where the invoice says 502667583.
    merged, _ = merge(_vision_bill(), parse(SAGE))
    assert merged.supplier_tax_id == "502667583"


def test_merge_warns_when_the_qr_contradicts_the_model():
    _, warnings = merge(_vision_bill(), parse(SAGE))
    assert any("502267583" in w and "502667583" in w for w in warnings)


def test_merge_is_silent_when_the_model_already_agreed():
    _, warnings = merge(_vision_bill(supplier_tax_id="502667583"), parse(SAGE))
    assert warnings == []


def test_merge_keeps_line_items_untouched():
    # The QR carries no line detail, so vision's lines must survive.
    merged, _ = merge(_vision_bill(), parse(SAGE))
    assert len(merged.lines) == 1
    assert merged.lines[0].description == "SubA Accountants"


def test_merge_fills_a_field_the_model_left_null_without_warning():
    merged, warnings = merge(_vision_bill(supplier_tax_id=None), parse(SAGE))
    assert merged.supplier_tax_id == "502667583"
    assert warnings == []  # filling a gap is not a disagreement


def test_merge_leaves_a_field_alone_when_the_qr_lacks_it():
    qr = parse("A:502667583*O:2532.23*N:473.51")
    merged, _ = merge(_vision_bill(), qr)
    assert merged.number == "FCL FCL-P26/029346"


def test_merge_warns_loudly_about_a_cancelled_document():
    qr = parse(SAGE.replace("*E:N*", "*E:A*"))
    _, warnings = merge(_vision_bill(), qr)
    assert any("cancel" in w.lower() for w in warnings)


def test_merge_warns_about_a_non_invoice_document_type():
    qr = parse(SAGE.replace("*D:FT*", "*D:NC*"))
    _, warnings = merge(_vision_bill(), qr)
    assert any("NC" in w for w in warnings)


def test_merge_does_not_warn_for_ordinary_invoice_types():
    for doc_type in ("FT", "FS", "FR"):
        qr = parse(SAGE.replace("*D:FT*", f"*D:{doc_type}*"))
        _, warnings = merge(_vision_bill(supplier_tax_id="502667583"), qr)
        assert warnings == [], f"{doc_type} should not warn"


def test_merge_does_not_mutate_the_original_bill():
    original = _vision_bill()
    merge(original, parse(SAGE))
    assert original.supplier_tax_id == "502267583"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_at_qr.py -v`
Expected: FAIL — `ImportError: cannot import name 'merge'`. The 13 Task 2 tests still pass.

- [ ] **Step 3: Write minimal implementation**

Append to `logic/bills/extract/at_qr.py`:

```python
from logic.bills.models import Bill

# Fields the QR overrides. Named identically on Bill and AtQr. Line items are
# absent by design: the QR carries no line detail, so vision remains the only
# source for them.
_MERGED = ("supplier_tax_id", "buyer_tax_id", "number", "issue_date",
           "net_total", "vat_total", "gross_total")

_INVOICE_TYPES = ("FT", "FS", "FR")


def merge(bill: Bill, qr: AtQr) -> tuple[Bill, list[str]]:
    """Overlay QR fields onto a vision-extracted bill.

    The QR is emitted by certified software and cannot misread a digit, so it
    wins every field it carries. Disagreements are reported rather than silently
    corrected — the operator should see what the model got wrong.
    """
    warnings: list[str] = []
    updates: dict[str, object] = {}

    for name in _MERGED:
        new = getattr(qr, name)
        if new is None:
            continue
        old = getattr(bill, name)
        updates[name] = new
        if old is not None and old != new:
            warnings.append(
                f"{name}: QR code reads {new!r}, extraction read {old!r} — using the QR")

    if qr.status is not None and qr.status != "N":
        warnings.append(
            f"QR code reports document status {qr.status!r} — this document may be "
            f"cancelled; do not post it without checking")
    if qr.doc_type is not None and qr.doc_type not in _INVOICE_TYPES:
        warnings.append(
            f"QR code reports document type {qr.doc_type!r}, which is not a purchase "
            f"invoice type ({', '.join(_INVOICE_TYPES)})")

    return bill.model_copy(update=updates), warnings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_at_qr.py -v`
Expected: PASS (23 tests)

- [ ] **Step 5: Commit**

```bash
git add logic/bills/extract/at_qr.py tests/bills/test_at_qr.py
git commit -m "feat(bills): merge AT QR fields over vision extraction"
```

---

### Task 4: Decode a QR from image bytes

The decoder library and image variant are whatever **Task 1's spike selected** — its report
names both. Implement against that choice. Complete code for either candidate is given below;
use the one Task 1 chose and delete the other.

**Files:**
- Create: `logic/bills/extract/qr.py`
- Modify: `pyproject.toml` (add the chosen dependency)
- Test: `tests/bills/test_qr.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `decode(data: bytes) -> str | None`. Task 5 calls it.

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_qr.py`:

```python
from pathlib import Path

import pytest

from logic.bills.extract.qr import decode

EXAMPLES = Path(__file__).resolve().parents[2] / "bills_examples"

# bills_examples/ is untracked; these tests skip rather than fail where it is absent.
pytestmark = pytest.mark.skipif(not EXAMPLES.is_dir(),
                                reason="bills_examples/ not present")


def test_decode_returns_none_for_non_image_bytes():
    assert decode(b"not an image at all") is None


def test_decode_returns_none_when_the_decoder_is_not_installed(monkeypatch):
    # Global constraint: a missing decoder must degrade to "no QR", never break
    # an upload. Simulate the library being absent.
    import builtins
    real_import = builtins.__import__

    def _no_decoder(name, *args, **kwargs):
        if name in ("cv2", "pyzbar", "pyzbar.pyzbar"):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_decoder)
    assert decode((EXAMPLES / "scanner_forumsi_1.jpeg").read_bytes()) is None


def test_decode_returns_none_for_an_invoice_without_a_qr():
    # scanner_forumsi_4 is a Spanish supplier's invoice and carries no AT QR.
    assert decode((EXAMPLES / "scanner_forumsi_4.jpeg").read_bytes()) is None


@pytest.mark.parametrize("name", [
    "scanner_forumsi_1.jpeg", "scanner_forumsi_2.jpeg", "scanner_forumsi_3.jpeg",
    "scanner_forumsi_5.jpeg", "scanner_forumsi_6.jpeg",
])
def test_decode_reads_the_at_payload(name):
    payload = decode((EXAMPLES / name).read_bytes())
    assert payload is not None, f"no QR decoded from {name}"
    assert payload.startswith("A:")
    assert "*O:" in payload
```

**If Task 1 found that some of these five do not decode**, mark exactly those with
`@pytest.mark.xfail(reason="QR too small to decode at 1080x1920", strict=True)` rather than
deleting them or weakening the assertion. `strict=True` means the test fails if it
unexpectedly starts passing, so improved capture resolution surfaces as a signal to update
the plan rather than passing silently.

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_qr.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.bills.extract.qr'`

- [ ] **Step 3: Write minimal implementation**

Create `logic/bills/extract/qr.py`. **Use the variant Task 1 selected.**

If the spike chose **OpenCV**:

```python
from __future__ import annotations

import io


def decode(data: bytes) -> str | None:
    """Return the AT QR payload found in an image, or None.

    Absence of a readable QR is the normal case, not a failure: many suppliers
    are foreign and print none. This never raises — a QR can only ever improve
    the extraction, never block it.

    Runs on the ORIGINAL bytes. `image.prepare` downscales to a 1568px long edge,
    which at observed invoice resolutions drops the QR below the roughly two
    pixels per module a decoder needs.

    Imports are function-local so the module loads where the decoder is absent.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageOps
    except ImportError:
        return None

    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
        detector = cv2.QRCodeDetector()
        for scale in (1, 2, 4):
            arr = np.array(img if scale == 1 else img.resize(
                (img.width * scale, img.height * scale), Image.LANCZOS))
            payload, _, _ = detector.detectAndDecode(arr)
            if payload:
                return payload
    except Exception:
        # Any decoder or image failure means "no QR", never a broken upload.
        return None
    return None
```

If the spike chose **pyzbar**:

```python
from __future__ import annotations

import io


def decode(data: bytes) -> str | None:
    """Return the AT QR payload found in an image, or None.

    Absence of a readable QR is the normal case, not a failure: many suppliers
    are foreign and print none. This never raises — a QR can only ever improve
    the extraction, never block it.

    Runs on the ORIGINAL bytes. `image.prepare` downscales to a 1568px long edge,
    which at observed invoice resolutions drops the QR below the roughly two
    pixels per module a decoder needs.

    Imports are function-local so the module loads where the decoder is absent.
    """
    try:
        from PIL import Image, ImageOps
        from pyzbar.pyzbar import ZBarSymbol, decode as zbar_decode
    except ImportError:
        return None

    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
        for scale in (1, 2, 4):
            scaled = img if scale == 1 else img.resize(
                (img.width * scale, img.height * scale), Image.LANCZOS)
            for found in zbar_decode(scaled, symbols=[ZBarSymbol.QRCODE]):
                payload = found.data.decode("utf-8", errors="replace")
                if payload.startswith("A:"):
                    return payload
    except Exception:
        # Any decoder or image failure means "no QR", never a broken upload.
        return None
    return None
```

Add the chosen package to `pyproject.toml`'s `dependencies` list, alongside `pillow`.

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_qr.py -v`
Expected: PASS, or PASS with the xfails Task 1's evidence justified.

- [ ] **Step 5: Commit**

```bash
git add logic/bills/extract/qr.py tests/bills/test_qr.py pyproject.toml
git commit -m "feat(bills): decode AT QR codes from invoice images"
```

---

### Task 5: Wire QR extraction into the upload path

**Files:**
- Modify: `logic/bills/service.py` (`upload` and `_extract`)
- Test: `tests/bills/test_service.py` (append)

**Interfaces:**
- Consumes: `decode` (Task 4), `parse` and `merge` (Tasks 2–3).
- Produces: no new public interface. `BillService.upload` keeps its signature; QR warnings join the existing `BillProposal.warnings`.

- [ ] **Step 1: Write the failing test**

Append to `tests/bills/test_service.py`:

```python
from logic.bills.extract import at_qr as at_qr_module


def test_upload_prefers_the_qr_supplier_nif_over_the_model(monkeypatch):
    payload = ("A:500100209*B:514380802*C:PT*D:FT*E:N*F:20260601*G:FT1*"
               "I7:100.00*I8:23.00*N:23.00*O:123.00")
    monkeypatch.setattr("logic.bills.service.decode", lambda data: payload)
    svc = _service(_reader_no_matches)
    proposal = svc.upload(b"%PDF-fake")
    assert proposal.bill.supplier_tax_id == "500100209"
    assert any("QR code reads" in w for w in proposal.warnings)


def test_upload_is_unchanged_when_no_qr_is_present(monkeypatch):
    monkeypatch.setattr("logic.bills.service.decode", lambda data: None)
    svc = _service(_reader_no_matches)
    proposal = svc.upload(b"%PDF-fake")
    # _bill()'s fixture NIF survives untouched.
    assert proposal.bill.supplier_tax_id == "500100209"
    assert all("QR code" not in w for w in proposal.warnings)


def test_upload_ignores_a_qr_that_is_not_an_at_code(monkeypatch):
    monkeypatch.setattr("logic.bills.service.decode",
                        lambda data: "https://example.com/some-other-qr")
    svc = _service(_reader_no_matches)
    assert svc.upload(b"%PDF-fake").bill.supplier_tax_id == "500100209"


def test_upload_keeps_arithmetic_warnings_alongside_qr_warnings(monkeypatch):
    payload = ("A:500100209*D:FT*E:A*F:20260601*G:FT1*N:23.00*O:123.00")
    monkeypatch.setattr("logic.bills.service.decode", lambda data: payload)
    svc = _service(_reader_no_matches)
    warnings = svc.upload(b"%PDF-fake").warnings
    assert any("cancel" in w.lower() for w in warnings)
```

Note: `_service()`'s `FakeParser` returns the shared `_bill()` fixture, whose
`supplier_tax_id` is `500100209` — a NIF with a valid check digit, changed in the previous
cycle so it survives the NIF guard.

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_service.py -v`
Expected: FAIL — `AttributeError: module 'logic.bills.service' has no attribute 'decode'`

- [ ] **Step 3: Write minimal implementation**

In `logic/bills/service.py`, add to the imports:

```python
from logic.bills.extract.at_qr import merge as merge_qr, parse as parse_qr
from logic.bills.extract.qr import decode
```

Change `_extract` to return the bill together with any QR warnings, and have `upload` merge
those warnings into the proposal's list. `_extract` currently returns `Bill`; it now returns
`tuple[Bill, list[str]]`:

```python
    def _extract(self, data: bytes) -> tuple[Bill, list[str]]:
        """PDFs go through Tesseract; images go straight to Claude vision, which
        reads skewed phone photos and preserves table layout that flat OCR text
        would destroy.

        A decoded AT QR then overrides whichever path produced the bill: it comes
        from certified software and cannot misread a digit."""
        media_type = sniff(data)
        if media_type == "application/pdf":
            bill = self._parser.parse(self._ocr(data))
        else:
            bill = self._parser.parse_image(*prepare(data, media_type))

        # decode() takes the ORIGINAL bytes: prepare() downscales past the point
        # where a QR this small survives.
        payload = decode(data)
        qr = parse_qr(payload) if payload else None
        return merge_qr(bill, qr) if qr else (bill, [])
```

Then in `upload`, unpack the pair and combine the warnings:

```python
    def upload(self, data: bytes) -> BillProposal:
        bill, qr_warnings = self._extract(data)
```

and build the proposal with `warnings=qr_warnings + arithmetic_warnings(bill)`, keeping the
existing NIF-guard warning logic exactly as it is — it runs after the merge, on the merged
bill.

**Before committing, check for other callers of `_extract`.** Its return type changes from
`Bill` to `tuple[Bill, list[str]]`, so any other call site — production or test — breaks.
Run `grep -rn "_extract" logic/ tests/` and fix whatever it finds. If the only caller is
`upload`, say so in your report rather than leaving it unstated.

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ -v`
Expected: PASS — the whole bills suite, 116 pre-existing plus everything added here.

- [ ] **Step 5: Commit**

```bash
git add logic/bills/service.py tests/bills/test_service.py
git commit -m "feat(bills): use AT QR data in preference to vision extraction"
```

---

### Task 6: Live verification

**Not committed.** Re-runs the six real invoices end to end and measures whether the QR
actually fixed what it was meant to fix.

- [ ] **Step 1:** Re-run the scratchpad `check_examples.py` from the previous cycle (see
  `.superpowers/sdd/2026-08-16-image-bill-ingestion/task-8-report.md`), unchanged — it calls
  the same pipeline, so QR extraction now takes effect automatically. Six API calls, one run.

- [ ] **Step 2:** Verify each result against its image, field by field, using the Read tool.

- [ ] **Step 3:** Report a before/after table against the previous cycle's measured baseline:

| File | `supplier_tax_id` before | after |
|---|---|---|
| 1 Sage | `502267583` (wrong, correct is `502667583`) | ? |
| 2 Vodafone | `502544180` (correct) | ? |
| 3 Atlante | `513989536` (correct) | ? |
| 4 Jotelulu | `ESB65814709` (correct, no QR — must be unchanged) | ? |
| 5 Alves & Catalão | `503448672` (correct) | ? |
| 6 Databox | `PT505939347` (correct) | ? |

State explicitly: how many invoices decoded a QR; whether `scanner_forumsi_1` reached
`502667583`; whether any field that was correct before is now wrong; and whether any warning
fired that should not have.

## Definition of Done

- [ ] `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ -v` green, with no pre-existing test removed or weakened.
- [ ] Task 6's before/after table exists and is reported.
- [ ] `scanner_forumsi_4.jpeg` (no QR) still extracts exactly as it did before.
- [ ] The 21 pre-existing `tests/chat` failures are unchanged — do not attempt to fix them here.
