from __future__ import annotations
import pytest

from logic.chat.pdf import PdfRenderer, ReportNotFound, WeasyPrintUnavailable


def test_register_returns_unique_ids():
    r = PdfRenderer()
    id1 = r.register("<p>1</p>", "T1")
    id2 = r.register("<p>2</p>", "T2")
    assert id1 != id2
    assert id1.startswith("r_")


def test_get_pdf_unknown_id_raises():
    r = PdfRenderer()
    with pytest.raises(ReportNotFound):
        r.get_pdf("r_does_not_exist")


def test_lru_eviction():
    r = PdfRenderer(max_entries=3)
    ids = [r.register(f"<p>{i}</p>", f"T{i}") for i in range(4)]
    with pytest.raises(ReportNotFound):
        r.get_pdf(ids[0])
    # newest 3 still resolvable
    assert r.has(ids[1]) and r.has(ids[2]) and r.has(ids[3])


def test_clear_drops_everything():
    r = PdfRenderer()
    rid = r.register("<p>x</p>", "T")
    r.clear()
    with pytest.raises(ReportNotFound):
        r.get_pdf(rid)


def test_get_pdf_renders_or_raises_unavailable(monkeypatch):
    r = PdfRenderer()
    rid = r.register("<p>Hello</p>", "Title")

    # Simulate weasyprint missing
    monkeypatch.setattr("logic.chat.pdf._weasyprint_available", lambda: False)
    with pytest.raises(WeasyPrintUnavailable):
        r.get_pdf(rid)


def test_pdf_renderer_css_param_defaults_to_empty():
    r = PdfRenderer()
    assert r._css == ""


def test_pdf_renderer_accepts_css():
    r = PdfRenderer(css="body { color: red; }")
    assert r._css == "body { color: red; }"
