from __future__ import annotations
import secrets
from collections import OrderedDict
from typing import NamedTuple


class ReportNotFound(Exception):
    pass


class Report(NamedTuple):
    title: str
    html: str


class ReportStore:
    """In-memory LRU. Reports are NOT persisted across server restarts —
    view_urls emitted from old conversations 404 after a restart."""
    def __init__(self, max_entries: int = 20) -> None:
        self._max = max_entries
        self._store: OrderedDict[str, Report] = OrderedDict()

    def register(self, html: str, title: str) -> str:
        rid = "r_" + secrets.token_hex(6)
        self._store[rid] = Report(title=title, html=html)
        self._store.move_to_end(rid)
        while len(self._store) > self._max:
            self._store.popitem(last=False)
        return rid

    def has(self, report_id: str) -> bool:
        return report_id in self._store

    def get(self, report_id: str) -> Report:
        if report_id not in self._store:
            raise ReportNotFound(report_id)
        return self._store[report_id]

    def clear(self) -> None:
        self._store.clear()
