import sys
import types
from types import SimpleNamespace

import pytest
from logic.bills import extract
from logic.bills.extract.media import UnsupportedMedia


def _install_fakes(monkeypatch, pages_text, raise_exc=None, page_count=None):
    """Stand in for pdf2image + pytesseract.

    pdfinfo_from_bytes reports the page count without rasterizing anything, and
    convert_from_bytes returns only the page range it was asked for — both
    mirror the real libraries, which is what lets pdf_to_text bound its memory.
    """
    fake_p2i = types.ModuleType("pdf2image")
    fake_tess = types.ModuleType("pytesseract")
    seen = SimpleNamespace(langs=[], ranges=[])

    def pdfinfo_from_bytes(_bytes):
        if raise_exc:
            raise raise_exc
        return {"Pages": len(pages_text) if page_count is None else page_count}

    def convert_from_bytes(_bytes, dpi=300, first_page=None, last_page=None):
        if raise_exc:
            raise raise_exc
        seen.ranges.append((first_page, last_page))
        return [f"IMG{first_page - 1}"]

    def image_to_string(img, lang=None):
        seen.langs.append(lang)
        return pages_text[int(str(img)[3:])]

    fake_p2i.pdfinfo_from_bytes = pdfinfo_from_bytes
    fake_p2i.convert_from_bytes = convert_from_bytes
    fake_tess.image_to_string = image_to_string
    monkeypatch.setitem(sys.modules, "pdf2image", fake_p2i)
    monkeypatch.setitem(sys.modules, "pytesseract", fake_tess)
    return seen


def test_pdf_to_text_returns_page_tagged_text(monkeypatch):
    from logic.bills.extract import ocr
    _install_fakes(monkeypatch, ["hello", "world"])
    pages = ocr.pdf_to_text(b"%PDF-fake")
    assert [p.page for p in pages] == [1, 2]
    assert pages[0].text == "hello" and pages[1].text == "world"


def test_pdf_to_text_ocrs_portuguese_by_default(monkeypatch):
    from logic.bills.extract import ocr
    seen = _install_fakes(monkeypatch, ["ola", "mundo"])
    ocr.pdf_to_text(b"%PDF-fake")
    assert seen.langs == ["por+eng", "por+eng"]


def test_pdf_to_text_raises_ocr_unavailable_on_missing_binary(monkeypatch):
    from logic.bills.extract import ocr
    _install_fakes(monkeypatch, [], raise_exc=Exception(
        "Unable to get page count. Is poppler installed?"))
    with pytest.raises(ocr.OcrUnavailable):
        ocr.pdf_to_text(b"%PDF-fake")


def test_pdf_to_text_rasterizes_one_page_at_a_time(monkeypatch):
    """A 300 dpi A4 page is ~25MB of RGB. Asking poppler for the whole document
    at once makes peak memory scale with page count, so each page is fetched,
    OCR'd and dropped on its own."""
    from logic.bills.extract import ocr
    seen = _install_fakes(monkeypatch, ["a", "b", "c"])
    ocr.pdf_to_text(b"%PDF-fake")
    assert seen.ranges == [(1, 1), (2, 2), (3, 3)]


def test_pdf_to_text_rejects_an_oversized_pdf(monkeypatch):
    from logic.bills.extract import ocr
    seen = _install_fakes(monkeypatch, ["x"])
    oversized = b"%PDF" + b"0" * ocr.MAX_UPLOAD_BYTES
    with pytest.raises(UnsupportedMedia):
        ocr.pdf_to_text(oversized)
    assert seen.ranges == [], "rejected before anything was rasterized"


def test_pdf_to_text_rejects_a_pdf_with_too_many_pages(monkeypatch):
    from logic.bills.extract import ocr
    seen = _install_fakes(monkeypatch, ["x"], page_count=ocr.MAX_PDF_PAGES + 1)
    with pytest.raises(UnsupportedMedia):
        ocr.pdf_to_text(b"%PDF-fake")
    assert seen.ranges == [], "page count is checked before any rasterizing"


def test_pdf_page_ceiling_clears_a_realistic_invoice():
    from logic.bills.extract import ocr
    assert ocr.MAX_PDF_PAGES >= 10
