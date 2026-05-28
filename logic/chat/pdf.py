from __future__ import annotations
import secrets
from collections import OrderedDict
from typing import Any


class ReportNotFound(Exception):
    pass


class WeasyPrintUnavailable(Exception):
    pass


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
        return True
    except Exception:
        return False


class PdfRenderer:
    def __init__(self, max_entries: int = 20, css: str = "") -> None:
        self._max = max_entries
        self._css = css
        self._store: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def register(self, html: str, title: str) -> str:
        rid = "r_" + secrets.token_hex(6)
        self._store[rid] = {"html": html, "title": title}
        self._store.move_to_end(rid)
        while len(self._store) > self._max:
            self._store.popitem(last=False)
        return rid

    def _has(self, report_id: str) -> bool:
        return report_id in self._store

    def get_pdf(self, report_id: str) -> bytes:
        if report_id not in self._store:
            raise ReportNotFound(report_id)
        if not _weasyprint_available():
            raise WeasyPrintUnavailable(
                "WeasyPrint is not installed or cannot be imported. "
                "Use the browser's Print > Save as PDF as a fallback."
            )
        import weasyprint
        entry = self._store[report_id]
        wrapped = (
            f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{entry['title']}</title>"
            f"<style>{self._css}</style></head>"
            f"<body>{entry['html']}</body></html>"
        )
        return weasyprint.HTML(string=wrapped).write_pdf()

    def clear(self) -> None:
        self._store.clear()
