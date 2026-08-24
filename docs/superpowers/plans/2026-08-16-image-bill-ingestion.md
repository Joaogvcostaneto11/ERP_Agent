# Image Bill Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept supplier invoices uploaded as JPEG/PNG/WebP/GIF images and extract them with Claude vision, producing the same `BillProposal` as the existing PDF path.

**Architecture:** `BillService.upload` sniffs the uploaded bytes by magic number and routes: PDFs keep going through Tesseract OCR to `BillParser.parse`, while images are EXIF-corrected, downscaled, base64-encoded and sent to `BillParser.parse_image` as a vision content block. Both parser paths share one completion helper so they cannot drift.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Pillow (already a dependency via pdf2image), Anthropic SDK, pytest.

**Spec:** [docs/superpowers/specs/2026-08-16-image-bill-ingestion-design.md](../specs/2026-08-16-image-bill-ingestion-design.md)

## Global Constraints

- Accepted formats: **JPEG, PNG, WebP, GIF** for images, plus the existing PDF. HEIC is rejected.
- Media type is determined by **magic bytes only** — never the filename or the client-supplied `Content-Type`.
- The PDF/Tesseract path must not change behavior. `ocr.pdf_to_text` is not modified.
- No OCR fallback when vision extraction fails.
- Image long edge is capped at **1568 px**; base64 payload capped at **5 MB**.
- All new errors subclass `RuntimeError` so `logic/bills/app.py` maps them to HTTP 400 unchanged.
- No new package dependencies. Pillow is already declared in `pyproject.toml`.
- Tests are offline and deterministic — no network, no real API calls, matching the existing `tests/bills/` fake-client style.
- Run tests with the clean interpreter outside OneDrive: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest`.

## File Structure

| File | Responsibility |
|---|---|
| `logic/bills/extract/media.py` (create) | Magic-byte media-type detection; owns `UnsupportedMedia` |
| `logic/bills/extract/image.py` (create) | EXIF orientation, downscale, base64 encoding, size ceiling |
| `logic/bills/extract/parser.py` (modify) | Adds `parse_image`; both paths share `_complete` |
| `logic/bills/service.py` (modify) | Routes upload bytes to the PDF or image path |
| `logic/bills/app.py` (modify) | Rename the now-misleading `pdf_bytes` local |
| `ui/bills/index.html` (modify) | Widen the file input's `accept` |
| `ui/bills/app.js` (modify) | "pick a PDF first" → "pick a file first" |
| `tests/bills/test_media.py` (create) | Sniffing per format, rejection of garbage and HEIC |
| `tests/bills/test_image.py` (create) | EXIF rotation, downscale, passthrough |
| `tests/bills/test_parser.py` (modify) | `parse_image` builds a correct image block |
| `tests/bills/test_service.py` (modify) | Routing: PDF → OCR, image → `parse_image` |
| `tests/bills/test_app.py` (modify) | Unsupported upload returns HTTP 400 |

---

### Task 1: Media-type detection

**Files:**
- Create: `logic/bills/extract/media.py`
- Test: `tests/bills/test_media.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `sniff(data: bytes) -> str` returning one of `"application/pdf"`, `"image/jpeg"`, `"image/png"`, `"image/webp"`, `"image/gif"`; and `class UnsupportedMedia(RuntimeError)`. Tasks 2, 4 import both from `logic.bills.extract.media`.

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_media.py`:

```python
import pytest

from logic.bills.extract.media import UnsupportedMedia, sniff

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
PDF = b"%PDF-1.7\n" + b"\x00" * 16
# ISO-BMFF/HEIC: the brand lives at offset 4, so nothing matches at offset 0.
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16


@pytest.mark.parametrize("data,expected", [
    (PDF, "application/pdf"),
    (JPEG, "image/jpeg"),
    (PNG, "image/png"),
    (WEBP, "image/webp"),
    (GIF, "image/gif"),
    (b"GIF87a" + b"\x00" * 16, "image/gif"),
])
def test_sniff_detects_accepted_formats(data, expected):
    assert sniff(data) == expected


@pytest.mark.parametrize("data", [HEIC, b"not a file at all", b"", b"RIFFxxxxAVI "])
def test_sniff_rejects_unsupported(data):
    with pytest.raises(UnsupportedMedia):
        sniff(data)


def test_unsupported_media_is_a_runtime_error():
    # app.py maps RuntimeError to HTTP 400; this keeps that mapping working.
    assert issubclass(UnsupportedMedia, RuntimeError)


def test_sniff_ignores_filename_and_trusts_bytes():
    # A PDF renamed to .jpg is still a PDF.
    assert sniff(PDF) == "application/pdf"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_media.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.bills.extract.media'`

- [ ] **Step 3: Write minimal implementation**

Create `logic/bills/extract/media.py`:

```python
from __future__ import annotations

ACCEPTED = "PDF, JPEG, PNG, WebP or GIF"


class UnsupportedMedia(RuntimeError):
    """The uploaded bytes are not a file type we can extract from."""


def sniff(data: bytes) -> str:
    """Identify the upload by magic bytes. Filenames and client-supplied
    Content-Type headers are user-controlled and routinely wrong coming from a
    phone upload chain, so neither is consulted."""
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    raise UnsupportedMedia(f"unsupported file type — upload a {ACCEPTED} file")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_media.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add logic/bills/extract/media.py tests/bills/test_media.py
git commit -m "feat(bills): detect upload media type by magic bytes"
```

---

### Task 2: Image preparation

**Files:**
- Create: `logic/bills/extract/image.py`
- Test: `tests/bills/test_image.py`

**Interfaces:**
- Consumes: `UnsupportedMedia` from `logic.bills.extract.media` (Task 1).
- Produces: `prepare(data: bytes, media_type: str) -> tuple[str, str]` returning `(media_type, base64_string)`. The returned media type is `"image/jpeg"` whenever the image was re-encoded, otherwise the one passed in. Task 4 calls it.

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_image.py`:

```python
import base64
import io

import pytest
from PIL import Image

from logic.bills.extract.image import MAX_EDGE, prepare
from logic.bills.extract.media import UnsupportedMedia


def _jpeg(size, orientation=None) -> bytes:
    img = Image.new("RGB", size, "white")
    buf = io.BytesIO()
    if orientation is None:
        img.save(buf, "JPEG")
    else:
        exif = img.getexif()
        exif[0x0112] = orientation  # EXIF Orientation tag
        img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def _decode(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def test_prepare_applies_exif_rotation():
    # Orientation 6 means "rotate 90 CW to display": a 40x20 landscape photo is
    # really a 20x40 portrait. Claude sees pixels, not metadata, so we must bake
    # the rotation in.
    media_type, b64 = prepare(_jpeg((40, 20), orientation=6), "image/jpeg")
    assert _decode(b64).size == (20, 40)
    assert media_type == "image/jpeg"


def test_prepare_downscales_long_edge():
    _, b64 = prepare(_jpeg((3000, 1500)), "image/jpeg")
    assert _decode(b64).size == (MAX_EDGE, MAX_EDGE // 2)


def test_prepare_passes_small_unrotated_image_through_untouched():
    data = _jpeg((100, 80))
    media_type, b64 = prepare(data, "image/jpeg")
    assert base64.b64decode(b64) == data
    assert media_type == "image/jpeg"


def test_prepare_preserves_media_type_when_untouched():
    img = Image.new("RGB", (50, 50), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    media_type, _ = prepare(buf.getvalue(), "image/png")
    assert media_type == "image/png"


def test_prepare_reencodes_resized_png_as_jpeg():
    img = Image.new("RGB", (2000, 1000), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    media_type, b64 = prepare(buf.getvalue(), "image/png")
    assert media_type == "image/jpeg"
    assert _decode(b64).size == (MAX_EDGE, MAX_EDGE // 2)


def test_prepare_rejects_undecodable_bytes():
    with pytest.raises(UnsupportedMedia):
        prepare(b"\xff\xd8\xff not really a jpeg", "image/jpeg")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_image.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'logic.bills.extract.image'`

- [ ] **Step 3: Write minimal implementation**

Create `logic/bills/extract/image.py`:

```python
from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from logic.bills.extract.media import UnsupportedMedia

MAX_EDGE = 1568       # the API downsamples past this, so larger is pure cost
MAX_B64_BYTES = 5 * 1024 * 1024
_ORIENTATION_TAG = 0x0112


def prepare(data: bytes, media_type: str) -> tuple[str, str]:
    """Return (media_type, base64) ready for a vision content block.

    Phone photos carry their rotation in EXIF metadata rather than in the
    pixels, so a sideways invoice would reach the model sideways without
    exif_transpose. Re-encoding is skipped entirely when the image needs
    neither rotation nor resizing, so the original bytes and media type
    survive untouched."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise UnsupportedMedia(f"could not read the image: {e}") from e

    rotated = img.getexif().get(_ORIENTATION_TAG, 1) not in (0, 1)
    img = ImageOps.exif_transpose(img)

    width, height = img.size
    scale = MAX_EDGE / max(width, height)
    resized = scale < 1
    if resized:
        img = img.resize((max(1, round(width * scale)), max(1, round(height * scale))),
                         Image.LANCZOS)

    if rotated or resized:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        data, media_type = buf.getvalue(), "image/jpeg"

    b64 = base64.b64encode(data).decode("ascii")
    if len(b64) > MAX_B64_BYTES:
        raise UnsupportedMedia("image is too large — send a smaller photo")
    return media_type, b64
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_image.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add logic/bills/extract/image.py tests/bills/test_image.py
git commit -m "feat(bills): prepare uploaded images for vision extraction"
```

---

### Task 3: Vision parsing

**Files:**
- Modify: `logic/bills/extract/parser.py` (replaces the `_SYSTEM` constant and the `parse` method)
- Test: `tests/bills/test_parser.py` (append; existing tests must keep passing)

**Interfaces:**
- Consumes: nothing from Tasks 1–2.
- Produces: `BillParser.parse_image(media_type: str, b64: str) -> Bill`. `BillParser.parse(pages: list[PageText]) -> Bill` keeps its existing signature. Task 4 calls both.

- [ ] **Step 1: Write the failing test**

Append to `tests/bills/test_parser.py`:

```python
def test_parse_image_sends_one_image_block():
    payload = {"supplier_name": "SAGE PORTUGAL", "lines": []}
    client = _FakeAnthropic(payload)
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    bill = parser.parse_image("image/png", "QUJD")

    assert bill.supplier_name == "SAGE PORTUGAL"
    content = client.last_kwargs["messages"][0]["content"]
    images = [b for b in content if b["type"] == "image"]
    assert len(images) == 1
    assert images[0]["source"] == {"type": "base64", "media_type": "image/png",
                                   "data": "QUJD"}


def test_parse_image_includes_field_hint_text():
    client = _FakeAnthropic({"supplier_name": "X", "lines": []})
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    parser.parse_image("image/jpeg", "QUJD")
    texts = [b["text"] for b in client.last_kwargs["messages"][0]["content"]
             if b["type"] == "text"]
    assert any("issue_date" in t for t in texts)


def test_system_prompt_forbids_guessing_illegible_values():
    client = _FakeAnthropic({"supplier_name": "X", "lines": []})
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    parser.parse_image("image/jpeg", "QUJD")
    system = client.last_kwargs["system"].lower()
    assert "null" in system and "guess" in system


def test_both_paths_describe_their_own_source():
    client = _FakeAnthropic({"supplier_name": "X", "lines": []})
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    parser.parse([PageText(page=1, text="t")])
    text_system = client.last_kwargs["system"]
    parser.parse_image("image/jpeg", "QUJD")
    image_system = client.last_kwargs["system"]
    assert "OCR text" in text_system
    assert "photograph" in image_system
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_parser.py -v`
Expected: FAIL — `AttributeError: 'BillParser' object has no attribute 'parse_image'` on the four new tests; the three pre-existing tests still PASS.

- [ ] **Step 3: Write minimal implementation**

In `logic/bills/extract/parser.py`, replace the `_SYSTEM` constant (lines 9–18) with:

```python
_SYSTEM_HEAD = "You extract structured data from a supplier invoice. "
_TEXT_SOURCE = "You are given the raw OCR text of the invoice pages. "
_IMAGE_SOURCE = "You are given a photograph or scan of the invoice. "
_SYSTEM_TAIL = (
    "Return ONLY a JSON object with these keys: "
    "supplier_name, supplier_tax_id, number, issue_date (YYYY-MM-DD), due_date "
    "(YYYY-MM-DD), currency, net_total, vat_total, gross_total, and lines (a list "
    "of objects with description, quantity, unit_price, vat_rate, total). Use null "
    "for anything not present. Amounts as decimal strings without currency symbols. "
    "vat_rate as a plain number without a percent sign (e.g. \"23\", not \"23%\"). "
    "Do not invent values. If a digit or field is not clearly legible, return null "
    "for it rather than guessing a plausible value."
)


def _system(source: str) -> str:
    return _SYSTEM_HEAD + source + _SYSTEM_TAIL
```

Then replace the `parse` method (lines 48–58) with:

```python
    def _complete(self, content: Any, system: str) -> Bill:
        resp = self._client.messages.create(
            model=self._model, max_tokens=2048, temperature=0,
            system=system,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(getattr(c, "text", "") for c in resp.content
                       if getattr(c, "type", None) == "text")
        return Bill.model_validate(_extract_json(text))

    def parse(self, pages: list[PageText]) -> Bill:
        joined = "\n\n".join(f"--- page {p.page} ---\n{p.text}" for p in pages)
        user = f"{field_hint(self._rule)}\n\nOCR TEXT:\n{joined}"
        return self._complete(user, _system(_TEXT_SOURCE))

    def parse_image(self, media_type: str, b64: str) -> Bill:
        content = [
            {"type": "image",
             "source": {"type": "base64", "media_type": media_type, "data": b64}},
            {"type": "text", "text": field_hint(self._rule)},
        ]
        return self._complete(content, _system(_IMAGE_SOURCE))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_parser.py -v`
Expected: PASS (7 tests — 3 pre-existing plus 4 new)

- [ ] **Step 5: Commit**

```bash
git add logic/bills/extract/parser.py tests/bills/test_parser.py
git commit -m "feat(bills): add vision parsing path to BillParser"
```

---

### Task 4: Upload routing

**Files:**
- Modify: `logic/bills/service.py:28-38` (the `upload` method)
- Modify: `logic/bills/app.py:84-86` (rename the misleading `pdf_bytes` local)
- Test: `tests/bills/test_service.py` (extend `FakeParser`, append two tests)

**Interfaces:**
- Consumes: `sniff` and `UnsupportedMedia` from `logic.bills.extract.media` (Task 1); `prepare` from `logic.bills.extract.image` (Task 2); `BillParser.parse_image` (Task 3).
- Produces: `BillService.upload(data: bytes) -> BillProposal` — same return type as before, parameter renamed from `pdf_bytes` to `data`. Callers pass positionally, so this is not a breaking change.

- [ ] **Step 1: Write the failing test**

In `tests/bills/test_service.py`, replace the existing `FakeParser` class with:

```python
class FakeParser:
    def __init__(self, bill):
        self._bill = bill
        self.image_calls = []
    def parse(self, pages): return self._bill
    def parse_image(self, media_type, b64):
        self.image_calls.append((media_type, b64))
        return self._bill
```

Then append:

```python
import base64
import io

import pytest
from PIL import Image

from logic.bills.extract.media import UnsupportedMedia


def _png_bytes(size=(60, 40)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, "PNG")
    return buf.getvalue()


def test_upload_routes_pdf_to_ocr():
    ocr_calls = []
    svc = _service(_reader_no_matches)
    svc._ocr = lambda data: ocr_calls.append(data) or []
    svc.upload(b"%PDF-1.7 fake")
    assert ocr_calls == [b"%PDF-1.7 fake"]
    assert svc._parser.image_calls == []


def test_upload_routes_image_to_vision_and_never_ocrs():
    def _boom(data):
        raise AssertionError("OCR must not run for an image upload")

    svc = _service(_reader_no_matches)
    svc._ocr = _boom
    data = _png_bytes()
    proposal = svc.upload(data)

    assert proposal.proposal_id.startswith("bill_")
    assert len(svc._parser.image_calls) == 1
    media_type, b64 = svc._parser.image_calls[0]
    assert media_type == "image/png"
    assert base64.b64decode(b64) == data


def test_upload_rejects_unsupported_bytes():
    svc = _service(_reader_no_matches)
    with pytest.raises(UnsupportedMedia):
        svc.upload(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16)
```

Note: `_service` builds the parser then overwrites `svc._parser` with a `FakeParser`, so `svc._parser.image_calls` is the fake's list.

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_service.py -v`
Expected: `test_upload_routes_image_to_vision_and_never_ocrs` FAILS with `AssertionError: OCR must not run for an image upload`, because today's `upload` sends every byte string to OCR. `test_upload_rejects_unsupported_bytes` also FAILS (no `UnsupportedMedia` is raised). `test_upload_routes_pdf_to_ocr` passes already — it pins existing behavior.

- [ ] **Step 3: Write minimal implementation**

In `logic/bills/service.py`, add to the imports at the top:

```python
from logic.bills.extract.image import prepare
from logic.bills.extract.media import sniff
```

Replace the `upload` method (lines 28–38) with:

```python
    def upload(self, data: bytes) -> BillProposal:
        bill = self._extract(data)
        supplier_match = self._matcher.match_supplier(bill)
        line_matches = [self._matcher.match_line(ln) for ln in bill.lines]
        proposal = BillProposal(
            proposal_id="bill_" + uuid.uuid4().hex[:12], bill=bill,
            supplier_match=supplier_match, line_matches=line_matches,
            warnings=arithmetic_warnings(bill))
        self._pending.put(proposal.proposal_id, proposal)
        return proposal

    def _extract(self, data: bytes) -> Bill:
        """PDFs go through Tesseract; images go straight to Claude vision, which
        reads skewed phone photos and preserves table layout that flat OCR text
        would destroy."""
        media_type = sniff(data)
        if media_type == "application/pdf":
            return self._parser.parse(self._ocr(data))
        return self._parser.parse_image(*prepare(data, media_type))
```

In `logic/bills/app.py`, change the upload handler body (lines 84–86) from `pdf_bytes` to `data`:

```python
    data = await file.read()
    try:
        proposal = get_service().upload(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ -v`
Expected: PASS — the whole bills suite, including the pre-existing 38 tests.

- [ ] **Step 5: Commit**

```bash
git add logic/bills/service.py logic/bills/app.py tests/bills/test_service.py
git commit -m "feat(bills): route image uploads to the vision path"
```

---

### Task 5: UI and end-to-end rejection

**Files:**
- Modify: `ui/bills/index.html:16`
- Modify: `ui/bills/app.js:19`
- Test: `tests/bills/test_app.py` (append)

**Interfaces:**
- Consumes: `UnsupportedMedia` from `logic.bills.extract.media` (Task 1).
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing test**

Append to `tests/bills/test_app.py`:

```python
from logic.bills.extract.media import UnsupportedMedia


def test_upload_accepts_an_image(monkeypatch):
    client = _client(monkeypatch)
    client.post("/bills/operator", json={"name": "alice"})
    r = client.post("/bills/upload",
                    files={"file": ("bill.jpeg", b"\xff\xd8\xff\xe0", "image/jpeg")})
    assert r.status_code == 200
    assert r.json()["proposal_id"] == "bill_x"


def test_upload_rejects_unsupported_type_with_400(monkeypatch):
    class RejectingService(StubService):
        def upload(self, data):
            raise UnsupportedMedia("unsupported file type — upload a PDF, JPEG, "
                                   "PNG, WebP or GIF file")

    monkeypatch.setattr(appmod, "get_service", lambda: RejectingService())
    client = TestClient(appmod.app)
    client.post("/bills/operator", json={"name": "alice"})
    r = client.post("/bills/upload",
                    files={"file": ("bill.heic", b"\x00\x00\x00\x18ftypheic",
                                    "image/heic")})
    assert r.status_code == 400
    assert "unsupported file type" in r.json()["detail"]
```

- [ ] **Step 2: Run the tests**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_app.py -v`
Expected: both new tests **PASS immediately**. This is deliberate and not a TDD step — the
service is stubbed out here, so these are regression guards on `app.py`'s existing
`RuntimeError` → HTTP 400 mapping, proving `UnsupportedMedia` reaches the operator as a
readable message rather than a 500. The actual new behavior in this task is the UI
`accept` attribute, which no Python test can exercise; it is verified by inspection in
Step 4 and for real in Task 6.

- [ ] **Step 3: Make the UI changes**

Update `StubService.upload` in `tests/bills/test_app.py` to match the new parameter name
(cosmetic — callers pass positionally, but leaving `pdf_bytes` there is now misleading):

```python
    def upload(self, data):
        return self._proposal
```

In `ui/bills/index.html` line 16:

```html
      <input type="file" id="file" accept="application/pdf,image/jpeg,image/png,image/webp,image/gif" />
```

In `ui/bills/app.js` line 19, replace `"pick a PDF first"` with `"pick a file first"`.

- [ ] **Step 4: Run the full suite and eyeball the input**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ -v`
Expected: PASS — full bills suite.

Then confirm `grep -n accept ui/bills/index.html` shows all five types, and that no
"pick a PDF" string survives: `grep -rni pdf ui/bills/` should return nothing.

- [ ] **Step 5: Commit**

```bash
git add ui/bills/index.html ui/bills/app.js tests/bills/test_app.py
git commit -m "feat(bills): accept image uploads in the bill ingestion UI"
```

---

### Task 6: Live accuracy check against the real examples

This task is **not committed**. It costs API credit and requires network. It is the only step that proves the system actually reads the invoices in `bills_examples/`; every earlier task only proves the plumbing.

**Files:**
- Create (scratchpad, do not commit): `<scratchpad>/check_examples.py`

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: printed JSON for operator review. No code depends on it.

- [ ] **Step 1: Write the script**

```python
"""Run every bills_examples image through the real vision path and print the
parsed Bill as JSON. Requires ANTHROPIC_API_KEY. Not part of the test suite."""
import json
import os
from pathlib import Path

import anthropic

from logic.bills.extract.image import prepare
from logic.bills.extract.media import sniff
from logic.bills.extract.parser import BillParser
from logic.bills.rules.loader import RuleLoader

ROOT = Path(__file__).resolve().parents[0]
REPO = Path(r"C:/Users/joaog/OneDrive/Documentos/GitHub/ERP_Agent")

parser = BillParser(anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"]),
                    "claude-sonnet-4-6",
                    RuleLoader(REPO / "business_rules" / "bills").rule())

for path in sorted((REPO / "bills_examples").glob("*.jpeg")):
    data = path.read_bytes()
    bill = parser.parse_image(*prepare(data, sniff(data)))
    print(f"\n===== {path.name} =====")
    print(json.dumps(bill.model_dump(mode="json"), indent=2, ensure_ascii=False))
```

- [ ] **Step 2: Run it**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe <scratchpad>/check_examples.py`
Expected: six JSON blocks, one per example file.

- [ ] **Step 3: Verify each result against the image**

For each of the six, open the image and check field by field:
`supplier_name`, `supplier_tax_id`, `number`, `issue_date`, `due_date`, `net_total`,
`vat_total`, `gross_total`, and each line's `description`, `quantity`, `unit_price`,
`vat_rate`, `total`.

For `scanner_forumsi_1.jpeg` specifically, the expected values are: supplier SAGE
Portugal, `number` `FCL FCL-P26/029346`, `issue_date` 2026-08-05, `due_date` 2026-10-04,
`gross_total` 2532.23, `vat_total` 473.51, and two lines (2498.28 and 37.56 unit prices at
20% line discount). Note the supplier's own NIF is *not* the `PT514380802` shown next to
`Cliente:` — that is FORUMSI's number, the buyer. If the model returns the buyer's tax ID
as `supplier_tax_id`, that is a real defect: report it rather than accepting it, since
supplier matching keys off that field.

- [ ] **Step 4: Report findings**

Summarize per file: correct, or which fields were wrong. Do not claim the feature works
until this table exists. If fields are systematically wrong, stop and discuss — the fix is
likely a prompt change, not more code.

---

---

### Task 7: Disambiguate supplier vs buyer tax ID

Added after Task 6's live run found `supplier_tax_id` correct on only 4 of 6 real invoices:
on `scanner_forumsi_2.jpeg` the model returned the buyer's NIF (labeled `Nº Contribuinte` in
the header) instead of the supplier's NIPC printed in the footer, and on
`scanner_forumsi_1.jpeg` it returned null although the supplier's NIPC was legible in the
footer. Header fields, dates, totals and arithmetic were correct on all six — this field is
the only extraction defect. It is load-bearing: supplier matching keys on it.

The fix is a prompt change plus a decoy field. Giving the model an explicit `buyer_tax_id`
slot forces it to separate the two numbers consciously rather than filling one slot with
whichever number it noticed first.

**Files:**
- Modify: `logic/bills/models.py` (the `Bill` model)
- Modify: `logic/bills/extract/parser.py` (`_SYSTEM_TAIL`, plus a new `_TAX_ID_RULE`)
- Test: `tests/bills/test_parser.py` (append)

**Interfaces:**
- Consumes: `BillParser.parse` / `parse_image` from Task 3.
- Produces: `Bill.buyer_tax_id: str | None`. Nothing writes it — no rule field in
  `business_rules/bills/purchase_invoice.yaml` maps to it, so it is extraction-only context.
  `supplier_tax_id` keeps its meaning and remains what `matching.py` keys on.

- [ ] **Step 1: Write the failing test**

Append to `tests/bills/test_parser.py`:

```python
def test_parse_image_extracts_buyer_tax_id_separately():
    payload = {"supplier_name": "VODAFONE PORTUGAL", "supplier_tax_id": "502544180",
               "buyer_tax_id": "514380802", "lines": []}
    parser = BillParser(_FakeAnthropic(payload), "claude-sonnet-4-6", _rule())
    bill = parser.parse_image("image/jpeg", "QUJD")
    assert bill.supplier_tax_id == "502544180"
    assert bill.buyer_tax_id == "514380802"


def test_buyer_tax_id_defaults_to_none_when_absent():
    parser = BillParser(_FakeAnthropic({"supplier_name": "X", "lines": []}),
                        "claude-sonnet-4-6", _rule())
    assert parser.parse_image("image/jpeg", "QUJD").buyer_tax_id is None


def test_system_prompt_disambiguates_the_two_tax_ids():
    client = _FakeAnthropic({"supplier_name": "X", "lines": []})
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    parser.parse_image("image/jpeg", "QUJD")
    system = client.last_kwargs["system"]
    assert "buyer_tax_id" in system
    # The issuer's number is often footer-only on Portuguese invoices.
    assert "footer" in system.lower()
    # The label alone is not decisive — both parties can carry "Contribuinte".
    assert "label" in system.lower()


def test_tax_id_rule_reaches_the_text_path_too():
    client = _FakeAnthropic({"supplier_name": "X", "lines": []})
    parser = BillParser(client, "claude-sonnet-4-6", _rule())
    parser.parse([PageText(page=1, text="t")])
    assert "buyer_tax_id" in client.last_kwargs["system"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/test_parser.py -v`
Expected: the four new tests FAIL — `Bill` has no `buyer_tax_id` attribute and the prompt
does not mention it. The seven pre-existing parser tests still PASS.

- [ ] **Step 3: Write minimal implementation**

In `logic/bills/models.py`, add one field to `Bill`, directly after `supplier_tax_id`:

```python
    buyer_tax_id: str | None = None
```

In `logic/bills/extract/parser.py`, add `buyer_tax_id` to the key list in `_SYSTEM_TAIL` so
it reads `supplier_name, supplier_tax_id, buyer_tax_id, number, ...`, then add this constant
after `_SYSTEM_TAIL`:

```python
_TAX_ID_RULE = (
    " This invoice was issued BY a supplier TO a buyer, so two tax numbers usually appear "
    "on the page. supplier_tax_id must be the ISSUER's — the company whose logo and address "
    "head the document. buyer_tax_id is the recipient's. Decide which number belongs to "
    "which party by whose address block it sits in, not by its label alone: the same label "
    "(Contribuinte, NIF, NIPC) appears next to either party depending on the invoice. On "
    "Portuguese invoices the issuer's number is often printed only in the footer, beside "
    "NIPC, Contribuinte, IVA, or a commercial-registry line — look there before returning "
    "null. Never put the buyer's number in supplier_tax_id. If only one tax number is "
    "visible, decide which party it belongs to and leave the other null."
)
```

Then append it in `_system` so both paths receive it:

```python
def _system(source: str) -> str:
    return _SYSTEM_HEAD + source + _SYSTEM_TAIL + _TAX_ID_RULE
```

- [ ] **Step 4: Run test to verify it passes**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ -v`
Expected: PASS — full bills suite, 69 pre-existing plus the 4 new.

- [ ] **Step 5: Commit**

```bash
git add logic/bills/models.py logic/bills/extract/parser.py tests/bills/test_parser.py
git commit -m "fix(bills): separate supplier and buyer tax IDs in extraction"
```

---

### Task 8: Re-run the live accuracy check

Same method as Task 6, same six files, same script. The measurement that matters is
`supplier_tax_id`: it was correct on 4 of 6 before Task 7.

- [ ] **Step 1:** Re-run the scratchpad script against all six `bills_examples` files.
- [ ] **Step 2:** Verify every file field-by-field against the image again — Task 7 changed
  the shared prompt, so fields that were correct before could have regressed. Do not check
  only the tax IDs.
- [ ] **Step 3:** Report a before/after table for `supplier_tax_id` and flag any field that
  was correct in Task 6 and is now wrong.

---

### Task 9: Close out the final-review regression and two weak tests

The final fix wave introduced one Important regression, reproduced end-to-end by the
re-reviewer, plus two tests that do not protect the code they were written for.

**Files:**
- Modify: `logic/bills/service.py` (the `stage()` method)
- Test: `tests/bills/test_service.py`, `tests/bills/test_image.py`

- [ ] **Step 1: Fix the stale-plan regression**

In `stage()`, the `except ValidationError` early return sits ABOVE
`self._pending.pop(proposal_id + ":plan")`, so a failed stage leaves the previously-staged
plan committable — `commit()` can then write a document from a plan whose stage call was
rejected. Move the pop above the `try` so it runs unconditionally. The comment already
states the invariant ("only a stage() call that ends ok:True can leave a committable plan
for commit()") — keep it with the moved line.

- [ ] **Step 2: Test that the regression stays fixed**

```python
def test_failed_stage_clears_a_previously_staged_plan():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF-fake")
    edited = proposal.model_dump(mode="json")
    assert svc.stage(proposal.proposal_id, edited)["ok"] is True

    # Second stage fails validation: the UI posts a cleared required field as null.
    edited["bill"]["supplier_name"] = None
    assert svc.stage(proposal.proposal_id, edited)["ok"] is False

    # The stale plan must not survive a rejected stage.
    with pytest.raises(RuntimeError):
        svc.commit(proposal.proposal_id, "alice")
```

- [ ] **Step 3: Make the two bomb tests honest**

In `tests/bills/test_image.py`, both
`test_prepare_rejects_oversized_upload_before_opening_it` and
`test_prepare_rejects_pixel_bomb_below_pillows_own_threshold` currently pass even with their
guard removed, because `prepare` normalises every exception to `UnsupportedMedia` and the
crafted PNG fails to decode anyway. Assert on the rejection MESSAGE so each test fails when
its own guard is deleted — the byte-ceiling test must see the byte-ceiling message, and the
pixel test must see the "too large to process" message that only the header check produces.

- [ ] **Step 4: Verify each test fails without its fix**

For each of the three tests, temporarily remove the guard it covers, confirm the test FAILS,
then restore. Record the failure output in the report. A test that passes with its guard
removed is not done.

- [ ] **Step 5: Run the suite and commit**

Run: `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ -v`

```bash
git add logic/bills/service.py tests/bills/test_service.py tests/bills/test_image.py
git commit -m "fix(bills): clear a stale write plan when stage() fails"
```

---

### Task 10: Reject a supplier tax ID that fails the Portuguese NIF check digit

The live run's residual defect: on `scanner_forumsi_1.jpeg` the model returns `502267583`
where the footer reads `502667583` — one misread digit, and a *wrong* value is worse than the
`null` it used to return, because supplier matching keys on this field.

Portuguese NIFs carry a check digit, so most single-digit misreads are detectable. A value
that fails the check is blanked and reported as a warning, rather than written as a plausible
wrong number.

**Verified against the real data** — all six suppliers' NIFs pass, and both observed misreads
fail:

| Value | Expected |
|---|---|
| `502667583` (Sage, correct) | valid |
| `502267583` (what the model returned) | **invalid** |
| `502544180` (Vodafone) | valid |
| `513989536` (Atlante) | valid |
| `503448672` (Alves & Catalão) | valid |
| `PT505939347` (Databox, prefixed) | valid |
| `514380802` (FORUMSI, the buyer) | valid |
| `514580802` (the buyer transposition) | **invalid** |
| `ESB65814709` (Jotelulu, Spanish VAT) | not PT-shaped — untouched |

**Files:**
- Create: `logic/bills/tax_id.py`
- Modify: `logic/bills/service.py` (`upload`)
- Test: `tests/bills/test_tax_id.py`, `tests/bills/test_service.py`

**Interfaces:**
- Produces: `pt_nif_is_valid(value: str) -> bool | None` — `True`/`False` for a
  Portuguese-shaped value, and `None` when the value is not PT-shaped and therefore not ours
  to judge.

- [ ] **Step 1: Write the failing test**

Create `tests/bills/test_tax_id.py` covering: every row of the table above; that a non-PT
value (`ESB65814709`, `""`, `None`, `"12345"`, `"50266758X"`) returns `None` rather than
`False`; and that an optional `PT` prefix and surrounding whitespace are tolerated.

- [ ] **Step 2: Run it and confirm it fails** (module does not exist).

- [ ] **Step 3: Implement**

The algorithm: strip whitespace and an optional leading `PT`. If what remains is not exactly
9 digits, return `None` — foreign tax IDs are not ours to judge. Otherwise weight the first
eight digits by 9, 8, 7, 6, 5, 4, 3, 2, sum them, take the sum modulo 11. The expected check
digit is 0 when the remainder is 0 or 1, otherwise 11 minus the remainder. Compare it to the
ninth digit.

- [ ] **Step 4: Wire it into upload**

In `BillService.upload`, after `_extract` and BEFORE matching (which keys on
`supplier_tax_id`): if `pt_nif_is_valid(bill.supplier_tax_id)` is `False`, blank the field to
`None` and add a warning naming the rejected value, so the operator sees what was discarded
and can type the right one. `None` and `True` both leave the field alone. Merge the warning
with `arithmetic_warnings(bill)` in the existing `warnings` list — do not invent a second
warning channel.

Only `supplier_tax_id` is validated. `buyer_tax_id` is extraction-only and nothing downstream
reads it.

- [ ] **Step 5: Test the wiring**

In `tests/bills/test_service.py`: a bill whose `supplier_tax_id` fails the check comes back
with the field blanked and a warning present, and the supplier match is NOT made on the bad
number. A bill with a valid NIF is untouched and warning-free. A bill with a Spanish VAT
number is untouched.

- [ ] **Step 6: Run the suite and commit**

```bash
git add logic/bills/tax_id.py logic/bills/service.py tests/bills/test_tax_id.py tests/bills/test_service.py
git commit -m "feat(bills): blank a supplier NIF that fails its check digit"
```

## Definition of Done

- [ ] `C:/Users/joaog/erp_venv/Scripts/python.exe -m pytest tests/bills/ -v` is green, with no pre-existing test removed or weakened.
- [ ] Task 6's accuracy table exists and is reported to the operator.
- [ ] `tests/chat` failures (21 pre-existing, unrelated) are unchanged — do not attempt to fix them here.
