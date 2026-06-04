# tests/devcare/test_audit_writer.py
import json
from logic.chat.audit import AuditLog
from logic.devcare.audit_writer import AuditWriter
from logic.devcare.errors import NormalizedChange


def test_writes_one_record(tmp_path):
    log = AuditLog(tmp_path / "writes.jsonl")
    writer = AuditWriter(log)
    change = NormalizedChange("specialty", "create", "Especialidades", "Chave",
                              {"Codigo": "Z9", "Nome": "Test"}, None)
    writer.record(operator="Joao", change=change, rule_doc="specialty",
                  rule_version=1, primary_key=7, before=None, status="ok")
    line = (tmp_path / "writes.jsonl").read_text(encoding="utf-8").strip()
    rec = json.loads(line)
    assert rec["kind"] == "devcare_write"
    assert rec["operator"] == "Joao"
    assert rec["operation"] == "create"
    assert rec["table"] == "Especialidades"
    assert rec["primary_key"] == 7
    assert rec["after"] == {"Codigo": "Z9", "Nome": "Test"}
    assert rec["rule_doc"] == "specialty" and rec["rule_version"] == 1
    assert rec["status"] == "ok"
    assert "ts" in rec


def test_delete_record_has_no_after(tmp_path):
    log = AuditLog(tmp_path / "deletes.jsonl")
    writer = AuditWriter(log)
    change = NormalizedChange("specialty", "delete", "Especialidades", "Chave", {}, 5)
    writer.record(operator="Joao", change=change, rule_doc="specialty",
                  rule_version=1, primary_key=5, before={"Nome": "Old"}, status="ok")
    line = (tmp_path / "deletes.jsonl").read_text(encoding="utf-8").strip()
    rec = json.loads(line)
    assert rec["operation"] == "delete"
    assert rec["after"] is None
    assert rec["before"] == {"Nome": "Old"}
    assert rec["status"] == "ok"
