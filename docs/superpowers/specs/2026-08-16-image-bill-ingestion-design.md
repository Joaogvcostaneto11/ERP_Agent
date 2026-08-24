# Image Bill Ingestion — Design

**Date:** 2026-08-16
**Status:** Approved
**Extends:** [2026-07-08-bill-ocr-ingestion-design.md](2026-07-08-bill-ocr-ingestion-design.md)

## Goal

Accept supplier invoices uploaded as image files (JPEG, PNG, WebP, GIF) in addition to
PDFs, producing the same `BillProposal` through the same match/stage/commit flow.

The motivating inputs are the six files in `bills_examples/`: phone photographs of
Portuguese invoices, taken at an angle on a desk, with the page background visible and
uneven lighting. Each file is one complete single-page invoice.

## Decisions

**Images are read by Claude vision, not Tesseract.** Tesseract performs badly on skewed,
unevenly lit photographs, and recovering from that means deskew/crop/binarize
preprocessing with no clear stopping point. Vision also preserves table layout, which
matters here: flattening the invoice grid to text loses which column a number belongs to
(`P.U. s/IVA` vs `Desc. Linha` vs `Total Líquido`).

**The PDF path is untouched.** It is tested and working. This change is a strict
addition; rasterizing PDFs to images and dropping Tesseract entirely is a separate
decision, to be made on its own evidence.

**No OCR fallback when vision fails.** A second extraction path doubles the failure modes
for no demonstrated gain.

**Formats are limited to what the vision API accepts natively:** JPEG, PNG, WebP, GIF.
HEIC — the iPhone camera default — is not accepted and is rejected with a message telling
the operator to convert to JPEG. Supporting it would add a `pillow-heif` dependency and
another package to provision on Render; deferred until someone actually hits it.

## Architecture

Upload keeps its one-file-in, one-proposal-out shape. `BillService.upload(data: bytes)`
keeps its exact signature and branches on the detected media type.

```
UploadFile bytes
      │
      ▼
  media.sniff(data)  ──── unknown ───►  UnsupportedMedia (RuntimeError) ──► HTTP 400
      │
      ├── application/pdf ──► ocr.pdf_to_text ──► parser.parse(pages)      [unchanged]
      │
      └── image/*        ──► image.prepare  ──► parser.parse_image(...)    [new]
                                                        │
                                                        ▼
                                                      Bill ──► Matcher ──► BillProposal
```

### `logic/bills/extract/media.py` (new)

`sniff(data: bytes) -> str` returns the media type from **magic bytes**, never from the
filename or the client-supplied `Content-Type`. Both are user-controlled and, through a
phone-to-browser upload chain, frequently wrong. Unknown signatures raise
`UnsupportedMedia(RuntimeError)`.

Signatures: `%PDF` → `application/pdf`; `\xFF\xD8\xFF` → `image/jpeg`; `\x89PNG\r\n\x1a\n`
→ `image/png`; `RIFF....WEBP` → `image/webp`; `GIF87a`/`GIF89a` → `image/gif`.

`UnsupportedMedia` subclasses `RuntimeError`, which `app.py`'s upload handler already
converts to a 400 carrying the detail string. No change to `app.py` is required.

### `logic/bills/extract/image.py` (new)

`prepare(data: bytes, media_type: str) -> tuple[str, str]` returning `(media_type, base64)`:

1. **Apply EXIF orientation** via `ImageOps.exif_transpose`. Phone cameras record rotation
   as metadata rather than rotating pixels; the model sees pixels, so without this a
   sideways invoice reaches Claude sideways.
2. **Downscale** so the long edge is at most 1568 px. The API downsamples beyond that
   anyway, so larger payloads cost tokens and latency for no added detail.
3. **Re-encode** as JPEG (quality 85) when the image was modified; pass the original bytes
   through untouched when it was not, preserving the declared media type.
4. **Reject** anything whose base64 payload still exceeds 5 MB, with a clear message.

Pillow is already installed as a `pdf2image` dependency — no new requirement.

### `logic/bills/extract/parser.py` (modified)

`BillParser.parse(pages)` stays as-is. A new `parse_image(media_type, b64)` builds a
message whose content is an image block plus the same `field_hint(rule)` text.

Both methods delegate to a shared private `_complete(content) -> Bill` holding the
existing response-text join, `_extract_json`, and `Bill.model_validate` — so the two paths
cannot drift apart.

The system prompt splits into a shared JSON contract plus a one-line source clause: "the
raw OCR text of the invoice pages" for the text path, "a photograph or scan of the
invoice" for the image path. The shared contract gains one rule:

> If a digit or field is not clearly legible, return null for it. Never guess a value.

This is the one failure mode the vision path introduces. OCR garbles numbers into
obviously broken text; a vision model can instead return a clean, plausible, wrong number.
An explicit null-over-guess instruction plus the existing `arithmetic_warnings` totals
check are the defenses.

### `ui/bills/index.html` (modified)

Widen the file input's `accept` to
`application/pdf,image/jpeg,image/png,image/webp,image/gif`.

## Error handling

| Condition | Behavior |
|---|---|
| Unrecognized magic bytes (incl. HEIC) | `UnsupportedMedia` → HTTP 400, detail names the accepted formats |
| Image too large after downscale | `UnsupportedMedia` → HTTP 400 |
| Corrupt/undecodable image | `UnsupportedMedia` → HTTP 400 |
| Vision returns no JSON | Existing `ValueError` from `_extract_json`, unchanged |
| Tesseract/Poppler missing | Existing `OcrUnavailable`, PDF path only, unchanged |

## Verification

**Offline tests** (`tests/bills/`, matching existing style, no network):

- `test_media.py` — each accepted signature sniffs correctly; garbage bytes and a HEIC
  header raise `UnsupportedMedia`.
- `test_image.py` — an EXIF-rotated synthetic image comes out upright; an oversized image
  is downscaled to a 1568 px long edge; a small image passes through unmodified with its
  media type preserved.
- `test_parser.py` — `parse_image` sends exactly one image block with the right
  `media_type` and base64 payload (mocked client); both paths produce the same `Bill` from
  the same JSON response.
- `test_service.py` — `upload` routes PDF bytes to the OCR function and image bytes to
  `parse_image`, and never calls the OCR function for an image.
- `test_app.py` — uploading an unsupported file returns 400 through `TestClient`.

**Live accuracy check:** a throwaway script running all six `bills_examples` files through
the real extraction path, printing each parsed `Bill` as JSON for field-by-field
comparison against the images. The offline tests prove the plumbing; only this proves the
system reads real invoices correctly. Not part of the committed test suite — it costs API
credit and requires network.

## Out of scope

- Multi-image upload for multi-page invoices (each example is a single-page bill).
- HEIC support.
- Any change to matching, staging, committing, or the write path.
- Replacing the PDF/Tesseract path.
