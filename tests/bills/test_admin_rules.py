import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import logic.bills.app as appmod

_SRC = Path(__file__).resolve().parents[2] / "business_rules" / "bills" / "purchase_invoice.yaml"

PATCH = {
    "rationale": "supplier's own code",
    "base_version": 1,
    "changes": [{"action": "set", "section": "lines", "name": "supplier_code",
                 "column": "CodigoForn", "source": "line.description",
                 "required": False}],
}

COLUMNS = {
    "Doc001": ["Chave", "Entidade", "Data", "Iliquido", "Total", "Obs", "DC", "OC", "Estado"],
    "LinDoc001": ["Documento", "ChaveProd", "Descricao", "Quantidade", "Punit", "CodigoForn"],
    "Entidades": ["Chave", "Nome", "NCont", "Tipo", "Listar"],
    "Artigos": ["Chave", "Nome", "Codigo"],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    shutil.copy(_SRC, tmp_path / "purchase_invoice.yaml")
    monkeypatch.setattr(appmod, "_RULES_DIR", tmp_path)
    monkeypatch.setattr(appmod, "_WRITE_LOG_PATH", tmp_path / "bills_writes.jsonl")
    monkeypatch.setenv("BILLS_ADMIN_TOKEN", "s3cret")

    def read(sql, params):
        return [{"COLUMN_NAME": c, "DATA_TYPE": "varchar", "IS_NULLABLE": "YES"}
                for c in COLUMNS.get(params["table"], [])]
    monkeypatch.setattr(appmod, "_read", read)

    class FakeProposer:
        def draft(self, prose, rule, schema):
            from logic.bills.rules.proposal import RuleChangeProposal
            return RuleChangeProposal.model_validate(PATCH)
    monkeypatch.setattr(appmod, "get_proposer", lambda: FakeProposer())

    appmod.reset_service()
    return TestClient(appmod.app)


def _h(token="s3cret"):
    return {"X-Admin-Token": token}


def test_routes_are_404_when_the_token_is_unset(client, monkeypatch):
    monkeypatch.delenv("BILLS_ADMIN_TOKEN", raising=False)
    assert client.get("/admin/rules/current", headers=_h()).status_code == 404
    assert client.get("/admin/rules/enabled").json() == {"enabled": False}


def test_wrong_token_is_403(client):
    assert client.get("/admin/rules/current", headers=_h("nope")).status_code == 403


def test_current_reports_version_schema_and_history(client):
    body = client.get("/admin/rules/current", headers=_h()).json()
    assert body["version"] == 1
    assert "CodigoForn" in body["schema"]["LinDoc001"]
    assert body["history"] == []


def test_draft_returns_a_validated_proposal_with_no_violations(client):
    r = client.post("/admin/rules/draft", headers=_h(),
                    json={"prose": "supplier code to CodigoForn"})
    assert r.status_code == 200
    assert r.json()["violations"] == []
    assert r.json()["proposal"]["changes"][0]["column"] == "CodigoForn"


def test_apply_bumps_the_version_and_audits(client, tmp_path):
    client.post("/admin/rules/apply", headers=_h(),
                json={"proposal": PATCH, "base_version": 1})
    assert client.get("/admin/rules/current", headers=_h()).json()["version"] == 2

    rows = [json.loads(l) for l in
            (tmp_path / "bills_writes.jsonl").read_text(encoding="utf-8").splitlines()]
    changes = [r for r in rows if r.get("kind") == "rule_change"]
    assert len(changes) == 1
    assert changes[0]["from_version"] == 1 and changes[0]["to_version"] == 2


def test_apply_with_a_stale_base_version_is_409_and_changes_nothing(client):
    client.post("/admin/rules/apply", headers=_h(),
                json={"proposal": PATCH, "base_version": 1})
    r = client.post("/admin/rules/apply", headers=_h(),
                    json={"proposal": PATCH, "base_version": 1})
    assert r.status_code == 409
    assert client.get("/admin/rules/current", headers=_h()).json()["version"] == 2


def test_apply_of_an_invalid_proposal_is_422_and_changes_nothing(client):
    bad = dict(PATCH, changes=[dict(PATCH["changes"][0], column="NoSuchColumn")])
    r = client.post("/admin/rules/apply", headers=_h(),
                    json={"proposal": bad, "base_version": 1})
    assert r.status_code == 422
    assert r.json()["violations"][0]["reason"]
    assert client.get("/admin/rules/current", headers=_h()).json()["version"] == 1


def test_apply_reloads_the_service_so_the_new_mapping_is_live(client):
    client.post("/admin/rules/apply", headers=_h(),
                json={"proposal": PATCH, "base_version": 1})
    from logic.bills.rules.store import RuleStore
    rule = RuleStore(appmod._RULES_DIR).current()
    assert rule.lines.fields["supplier_code"].column == "CodigoForn"
    assert appmod._service is None      # reset; rebuilt lazily on next request


def test_revert_walks_forward_to_a_new_version(client):
    client.post("/admin/rules/apply", headers=_h(),
                json={"proposal": PATCH, "base_version": 1})
    r = client.post("/admin/rules/revert/1", headers=_h())
    assert r.status_code == 200
    assert r.json()["version"] == 3


def test_revert_to_an_unknown_version_is_404(client):
    assert client.post("/admin/rules/revert/99", headers=_h()).status_code == 404


def test_a_schema_outage_is_503_not_a_silent_rejection(client, monkeypatch):
    def broken(sql, params):
        raise OSError("connection reset")
    monkeypatch.setattr(appmod, "_read", broken)
    appmod.reset_service()          # drop the cached probe
    r = client.get("/admin/rules/current", headers=_h())
    assert r.status_code == 503
