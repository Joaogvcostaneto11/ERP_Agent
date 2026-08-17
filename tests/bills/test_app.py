from decimal import Decimal
from fastapi.testclient import TestClient

import logic.bills.app as appmod
from logic.bills.models import Bill, BillLine, BillProposal, MatchResult
from logic.bills.extract.media import UnsupportedMedia


class StubService:
    def __init__(self):
        self._proposal = BillProposal(
            proposal_id="bill_x", bill=Bill(supplier_name="ACME"),
            supplier_match=MatchResult(status="matched", chave=7),
            line_matches=[], warnings=[])
    def upload(self, data):
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


def test_upload_accepts_an_image(monkeypatch):
    class RecordingService(StubService):
        def __init__(self):
            super().__init__()
            self.received_data = None
        def upload(self, data):
            self.received_data = data
            return self._proposal

    recording_stub = RecordingService()
    monkeypatch.setattr(appmod, "get_service", lambda: recording_stub)
    client = TestClient(appmod.app)
    client.post("/bills/operator", json={"name": "alice"})
    image_bytes = b"\xff\xd8\xff\xe0"
    r = client.post("/bills/upload",
                    files={"file": ("bill.jpeg", image_bytes, "image/jpeg")})
    assert r.status_code == 200
    assert r.json()["proposal_id"] == "bill_x"
    assert recording_stub.received_data == image_bytes


def test_upload_rejects_unsupported_type_with_400(monkeypatch):
    class RejectingService(StubService):
        def upload(self, data):
            raise UnsupportedMedia("unsupported file type — upload a PDF, JPEG, "
                                   "PNG, WebP or GIF file")

    monkeypatch.setattr(appmod, "get_service", lambda: RejectingService())
    client = TestClient(appmod.app)
    client.post("/bills/operator", json={"name": "alice"})
    r = client.post("/bills/upload",
                    files={"file": ("bill.heic", b"\x00\x00\x00\x18ftypheic",
                                    "image/heic")})
    assert r.status_code == 400
    assert "unsupported file type" in r.json()["detail"]
