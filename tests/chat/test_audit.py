from __future__ import annotations
import json
from pathlib import Path

from logic.chat.audit import AuditLog


def test_append_writes_one_jsonl_line(tmp_log_path: Path):
    log = AuditLog(tmp_log_path)
    log.append({"ts": "2026-05-28T10:00:00Z", "sql": "SELECT 1", "rows": 1, "status": "ok"})
    contents = tmp_log_path.read_text(encoding="utf-8")
    assert contents.count("\n") == 1
    parsed = json.loads(contents.strip())
    assert parsed["sql"] == "SELECT 1"


def test_append_creates_parent_directory(tmp_path: Path):
    nested = tmp_path / "deep" / "queries.jsonl"
    log = AuditLog(nested)
    log.append({"x": 1})
    assert nested.exists()


def test_append_multiple_entries(tmp_log_path: Path):
    log = AuditLog(tmp_log_path)
    for i in range(3):
        log.append({"i": i})
    lines = tmp_log_path.read_text(encoding="utf-8").strip().splitlines()
    assert [json.loads(line)["i"] for line in lines] == [0, 1, 2]


def test_append_does_not_raise_on_write_failure(tmp_path: Path, monkeypatch):
    log = AuditLog(tmp_path / "queries.jsonl")

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom)
    log.append({"x": 1})  # must not raise


def test_now_iso_format():
    s = AuditLog.now_iso()
    # 2026-05-28T14:23:11.123Z shape
    assert s.endswith("Z")
    assert "T" in s
