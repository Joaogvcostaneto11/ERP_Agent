from __future__ import annotations
import pytest

from logic.chat.report_store import Report, ReportNotFound, ReportStore


def test_register_returns_unique_ids():
    s = ReportStore()
    id1 = s.register("<p>1</p>", "T1")
    id2 = s.register("<p>2</p>", "T2")
    assert id1 != id2
    assert id1.startswith("r_")


def test_get_returns_report_tuple():
    s = ReportStore()
    rid = s.register("<p>Hello</p>", "Title")
    r = s.get(rid)
    assert isinstance(r, Report)
    assert r.title == "Title"
    assert r.html == "<p>Hello</p>"


def test_get_unknown_id_raises():
    s = ReportStore()
    with pytest.raises(ReportNotFound):
        s.get("r_does_not_exist")


def test_has_reflects_presence():
    s = ReportStore()
    rid = s.register("<p>x</p>", "T")
    assert s.has(rid)
    assert not s.has("r_missing")


def test_lru_eviction():
    s = ReportStore(max_entries=3)
    ids = [s.register(f"<p>{i}</p>", f"T{i}") for i in range(4)]
    assert not s.has(ids[0])
    assert s.has(ids[1]) and s.has(ids[2]) and s.has(ids[3])


def test_clear_drops_everything():
    s = ReportStore()
    rid = s.register("<p>x</p>", "T")
    s.clear()
    assert not s.has(rid)
