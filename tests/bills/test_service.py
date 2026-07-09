from decimal import Decimal
from pathlib import Path

from logic.bills.models import Bill, BillLine
from logic.bills.pending import PendingProposalStore
from logic.bills.rules.loader import RuleLoader
from logic.bills.service import BillService

RULES_DIR = Path(__file__).resolve().parents[2] / "business_rules" / "bills"


class FakeParser:
    def __init__(self, bill): self._bill = bill
    def parse(self, pages): return self._bill


class FakeExecutor:
    def __init__(self): self.calls = []
    def execute(self, plan, rule):
        self.calls.append(plan)
        return {"document_chave": 99, "supplier_chave": 7, "line_chaves": [1],
                "created_supplier": False, "created_articles": []}


class FakeAudit:
    def __init__(self): self.records = []
    def record(self, **kw): self.records.append(kw)


def _reader_no_matches(sql, params):
    return []


def _reader_supplier_and_article(sql, params):
    if "Entidades" in sql and params.get("tax_id") == "500100200":
        return [{"Chave": 7, "Nome": "ACME"}]
    if "Artigos" in sql:
        return [{"Chave": 42, "Nome": "Widget"}]
    return []


def _bill():
    return Bill(supplier_name="ACME", supplier_tax_id="500100200",
                number="FT1", issue_date="2026-06-01", net_total=Decimal("100"),
                vat_total=Decimal("23"), gross_total=Decimal("123"),
                lines=[BillLine(description="Widget", quantity=Decimal("2"),
                                unit_price=Decimal("50"), vat_rate=Decimal("23"),
                                total=Decimal("100"))])


def _service(reader, executor=None, monkeypatch_ocr=None):
    svc = BillService(anthropic_client=None, ocr_fn=lambda b: [],
                      rule=RuleLoader(RULES_DIR).rule(), reader=reader,
                      pending=PendingProposalStore(), executor=executor or FakeExecutor(),
                      audit=FakeAudit(), model="claude-sonnet-4-6")
    svc._parser = FakeParser(_bill())  # inject parser (constructor builds a real one)
    return svc


def test_upload_produces_matched_proposal():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    assert proposal.supplier_match.status == "matched"
    assert proposal.line_matches[0].status == "matched"
    assert svc._pending.get(proposal.proposal_id) is not None


def test_upload_flags_new_supplier_and_article():
    svc = _service(_reader_no_matches)
    proposal = svc.upload(b"%PDF")
    assert proposal.supplier_match.status == "new"
    assert proposal.line_matches[0].status == "new"


def test_stage_rejects_unconfirmed_new_records():
    svc = _service(_reader_no_matches)
    proposal = svc.upload(b"%PDF")
    result = svc.stage(proposal.proposal_id, proposal.model_dump(mode="json"))
    assert result["ok"] is False
    assert any("confirm" in v["message"].lower() for v in result["violations"])


def test_stage_rejects_missing_required_total():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    edited = proposal.model_dump(mode="json")
    edited["bill"]["gross_total"] = None
    result = svc.stage(proposal.proposal_id, edited)
    assert result["ok"] is False
    assert any("total" in v["message"].lower() for v in result["violations"])


def test_stage_then_commit_writes_and_audits():
    executor = FakeExecutor()
    svc = _service(_reader_supplier_and_article, executor=executor)
    proposal = svc.upload(b"%PDF")
    staged = svc.stage(proposal.proposal_id, proposal.model_dump(mode="json"))
    assert staged["ok"] is True
    out = svc.commit(proposal.proposal_id, operator="alice")
    assert out["status"] == "ok" and out["document_chave"] == 99
    assert len(executor.calls) == 1
    assert svc._audit.records[0]["status"] == "ok"
    # proposal consumed
    assert svc.commit(proposal.proposal_id, operator="alice")["status"] == "error"


def test_failing_restage_clears_prior_valid_plan():
    executor = FakeExecutor()
    svc = _service(_reader_supplier_and_article, executor=executor)
    proposal = svc.upload(b"%PDF")
    # first stage succeeds and stashes a plan
    assert svc.stage(proposal.proposal_id, proposal.model_dump(mode="json"))["ok"] is True
    # operator edits into an invalid state and re-stages
    edited = proposal.model_dump(mode="json")
    edited["bill"]["gross_total"] = None
    assert svc.stage(proposal.proposal_id, edited)["ok"] is False
    # commit must NOT execute the stale, previously-valid plan
    out = svc.commit(proposal.proposal_id, operator="alice")
    assert out["status"] == "error"
    assert executor.calls == []


def test_stage_rejects_ambiguous_supplier_without_choice():
    svc = _service(_reader_supplier_and_article)
    proposal = svc.upload(b"%PDF")
    edited = proposal.model_dump(mode="json")
    edited["supplier_match"] = {
        "status": "ambiguous", "chave": None,
        "candidates": [{"chave": 1, "label": "A", "score": 1.0},
                       {"chave": 2, "label": "B", "score": 1.0}],
        "proposed_new": None, "confirmed": False}
    result = svc.stage(proposal.proposal_id, edited)
    assert result["ok"] is False
    assert any(("candidate" in v["message"].lower()) or ("pick" in v["message"].lower())
               for v in result["violations"])
