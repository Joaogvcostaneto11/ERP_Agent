import json
from logic.chat.audit import AuditLog
from logic.bills.audit_writer import BillAuditWriter
from logic.bills.models import LinePlan, MatchResult, WritePlan


def _plan():
    return WritePlan(proposal_id="p1", supplier=MatchResult(status="matched", chave=7),
                     header={"Total": "123"}, lines=[], rule_doc="purchase_invoice",
                     rule_version=1)


def test_record_writes_one_audit_line(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    writer = BillAuditWriter(log)
    result = {"document_chave": 55, "supplier_chave": 7, "line_chaves": [1, 2],
              "created_supplier": False, "created_articles": []}
    writer.record(operator="alice", plan=_plan(), result=result, status="ok")
    entries = [json.loads(l) for l in (tmp_path / "a.jsonl").read_text().splitlines()]
    assert len(entries) == 1
    e = entries[0]
    assert e["kind"] == "bill_ingest" and e["operator"] == "alice"
    assert e["proposal_id"] == "p1" and e["document_chave"] == 55
    assert e["rule_doc"] == "purchase_invoice" and e["rule_version"] == 1
    assert e["status"] == "ok"
