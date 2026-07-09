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
    _install_fakes(monkeypatch, [], raise_exc=Exception("Unable to get page count. Is poppler installed?"))
    with pytest.raises(ocr.OcrUnavailable):
        ocr.pdf_to_text(b"%PDF-fake")
