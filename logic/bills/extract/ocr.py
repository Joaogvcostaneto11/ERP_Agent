from __future__ import annotations

from logic.bills.models import PageText
from logic.bills.extract.media import MAX_UPLOAD_BYTES, UnsupportedMedia


class OcrUnavailable(RuntimeError):
    """Tesseract or Poppler is not installed/reachable on the host."""


# A supplier invoice is a handful of pages. This is not a page count anyone
# would hit by accident, and past it the rasterizing below stops being worth
# the wait even though its memory is bounded.
MAX_PDF_PAGES = 20


def pdf_to_text(pdf_bytes: bytes, *, dpi: int = 300, lang: str = "por+eng") -> list[PageText]:
    """Rasterize each PDF page and OCR it. Imports are function-local so the
    module loads even where the binaries are absent (they're only needed at call
    time). Feeding the page image to Claude alongside this text is a future
    drop-in: keep this the single extraction entry point.

    `lang` defaults to Portuguese plus English: supplier invoices are Portuguese
    but routinely carry English terms and product names. The host must have the
    matching traineddata (`tesseract-ocr-por`) or Tesseract fails the call.

    Size and page count are both bounded before any rasterizing happens, and
    pages are then converted one at a time — see the loop below.
    """
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        raise UnsupportedMedia("PDF file is too large — send a smaller file")
    try:
        from pdf2image import convert_from_bytes, pdfinfo_from_bytes
        import pytesseract
    except ImportError as e:  # pragma: no cover - packaging guard
        raise OcrUnavailable(str(e)) from e
    try:
        # Reads the trailer only; nothing is rasterized to answer this.
        page_count = int(pdfinfo_from_bytes(pdf_bytes)["Pages"])
    except Exception as e:
        raise OcrUnavailable(str(e)) from e
    if page_count > MAX_PDF_PAGES:
        raise UnsupportedMedia(
            f"PDF has {page_count} pages — the limit is {MAX_PDF_PAGES}")
    try:
        pages = []
        for n in range(1, page_count + 1):
            # One page per call. convert_from_bytes returns every page it is
            # asked for as a full RGB bitmap (~25MB for A4 at 300 dpi), so
            # converting the whole document in one call makes peak memory scale
            # with page count. Re-reading the PDF each time costs far less than
            # holding twenty bitmaps at once.
            image = convert_from_bytes(
                pdf_bytes, dpi=dpi, first_page=n, last_page=n)[0]
            pages.append(PageText(
                page=n, text=pytesseract.image_to_string(image, lang=lang)))
        return pages
    except Exception as e:
        # pdf2image/pytesseract raise heterogeneous, non-OSError types when the
        # Poppler/Tesseract binaries are missing (e.g. pdf2image's
        # PDFInfoNotInstalledError subclasses plain Exception). Normalize every
        # extraction failure to OcrUnavailable — the wrapper's contract.
        raise OcrUnavailable(str(e)) from e
