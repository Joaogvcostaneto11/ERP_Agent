from __future__ import annotations

from logic.bills.models import PageText


class OcrUnavailable(RuntimeError):
    """Tesseract or Poppler is not installed/reachable on the host."""


def pdf_to_text(pdf_bytes: bytes, *, dpi: int = 300, lang: str = "por+eng") -> list[PageText]:
    """Rasterize each PDF page and OCR it. Imports are function-local so the
    module loads even where the binaries are absent (they're only needed at call
    time). Feeding the page image to Claude alongside this text is a future
    drop-in: keep this the single extraction entry point.

    `lang` defaults to Portuguese plus English: supplier invoices are Portuguese
    but routinely carry English terms and product names. The host must have the
    matching traineddata (`tesseract-ocr-por`) or Tesseract fails the call."""
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
    except ImportError as e:  # pragma: no cover - packaging guard
        raise OcrUnavailable(str(e)) from e
    try:
        images = convert_from_bytes(pdf_bytes, dpi=dpi)
        return [PageText(page=i + 1, text=pytesseract.image_to_string(img, lang=lang))
                for i, img in enumerate(images)]
    except Exception as e:
        # pdf2image/pytesseract raise heterogeneous, non-OSError types when the
        # Poppler/Tesseract binaries are missing (e.g. pdf2image's
        # PDFInfoNotInstalledError subclasses plain Exception). Normalize every
        # extraction failure to OcrUnavailable — the wrapper's contract.
        raise OcrUnavailable(str(e)) from e
