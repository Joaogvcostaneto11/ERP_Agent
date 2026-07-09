from decimal import Decimal
from fastapi.testclient import TestClient

import logic.bills.app as appmod
from logic.bills.models import Bill, BillLine, BillProposal, MatchResult


class StubService:
    def __init__(self):
        self._proposal = BillProposal(
            proposal_id="bill_x", bill=Bill(supplier_name="ACME"),
            supplier_match=MatchResult(status="matched", chave=7),
            line_matches=[], warnings=[])
    def upload(self, pdf_bytes):
        return self._proposal
    def stage(self, proposal_id, edited):
        return {"ok": True, "write_plan": {"proposal_id": proposal_id}, "warnings": []}
    def commit(self, proposal_id, operator):
        return {"status": "ok", "document_chave": 99}


def _client(monkeypatch):
    monkeypatch.setattr(appmod, "get_service", lambda: StubService())
    return TestClient(appmod.app)


def test_upload_returns_proposal(monkeypatch):
    client = _client(monkeypatch)
    client.post("/bills/operator", json={"name": "alice"})
    r = client.post("/bills/upload", files={"file": ("b.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 200
    assert r.json()["proposal_id"] == "bill_x"


def test_commit_requires_operator(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/bills/commit/bill_x", json={})
    assert r.status_code == 400


def test_stage_then_commit(monkeypatch):
    client = _client(monkeypatch)
    client.post("/bills/operator", json={"name": "alice"})
    assert client.post("/bills/stage/bill_x", json={"proposal_id": "bill_x"}).json()["ok"] is True
    assert client.post("/bills/commit/bill_x", json={}).json()["document_chave"] == 99
