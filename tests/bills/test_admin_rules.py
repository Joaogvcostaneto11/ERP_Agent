import json
import shutil
from pathlib import Path

import pytest
from contextlib import contextmanager
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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


def _sqlite_rules_factory(tmp_path):
    """SQLite stand-in for ERPAgent_BillRules, as tests/bills/test_rule_store.py
    and test_write_executor.py do for their tables."""
    eng = create_engine(f"sqlite:///{tmp_path/'rules.db'}")
    with eng.begin() as c:
        c.execute(text(
            "CREATE TABLE ERPAgent_BillRules ("
            " Version INTEGER NOT NULL PRIMARY KEY, Yaml TEXT NOT NULL,"
            " Ts TEXT NOT NULL, Action TEXT NOT NULL, Operator TEXT,"
            " Prose TEXT, Rationale TEXT, Changes TEXT, RevertedTo INTEGER)"))
    Local = sessionmaker(bind=eng)

    @contextmanager
    def factory():
        sess = Local()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    return factory


@pytest.fixture
def client(tmp_path, monkeypatch):
    # _RULES_DIR is the seed for an empty table now, not the store itself.
    shutil.copy(_SRC, tmp_path / "purchase_invoice.yaml")
    monkeypatch.setattr(appmod, "_RULES_DIR", tmp_path)
    monkeypatch.setattr(appmod, "_TABLE_PREFIX", "")
    monkeypatch.setattr(appmod, "get_bills_write_session",
                        _sqlite_rules_factory(tmp_path))
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


def test_a_non_ascii_token_is_403_not_500(client):
    # m4: secrets.compare_digest raises TypeError on non-ASCII str, which is
    # reachable from a typo'd paste. A bad token is a 403, not a server fault.
    # Sent as bytes because httpx refuses to encode a non-ASCII str header;
    # a browser sends the same bytes, and starlette decodes them latin-1 into
    # the non-ASCII str that compare_digest chokes on.
    r = client.get("/admin/rules/current",
                   headers={"X-Admin-Token": "s3crét".encode("utf-8")})
    assert r.status_code == 403


def test_a_non_ascii_configured_token_authenticates_when_matched(monkeypatch):
    # A non-ASCII BILLS_ADMIN_TOKEN must not be a silent permanent lockout:
    # comparing UTF-8 bytes lets a correctly-supplied non-ASCII configured
    # token authenticate, not just fail loudly. Exercised directly against
    # _require_admin rather than through TestClient/httpx: that stack forces
    # non-ASCII header bytes through str round-trips with mixed encodings
    # (utf-8 then latin-1) that can never reproduce a byte-exact non-ASCII
    # header, so it cannot be used to observe the fixed comparison succeed.
    monkeypatch.setenv("BILLS_ADMIN_TOKEN", "s3crét")

    class _FakeHeaders(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    class _FakeRequest:
        def __init__(self, headers):
            self.headers = _FakeHeaders(headers)

    appmod._require_admin(_FakeRequest({"X-Admin-Token": "s3crét"}))  # no raise


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


def _rule_change_rows(tmp_path):
    return [json.loads(l) for l
            in (tmp_path / "bills_writes.jsonl").read_text(encoding="utf-8").splitlines()
            if json.loads(l).get("kind") == "rule_change"]


def test_the_audit_row_keeps_the_admins_own_prose(client, tmp_path):
    # I4: `rationale` is Claude's paraphrase. The audit trail is
    # non-negotiable and the human author's actual words are what it must not
    # lose, so the prose is recorded as a field of its own.
    client.post("/admin/rules/apply", headers=_h(), json={
        "proposal": PATCH, "base_version": 1,
        "prose": "  put the supplier's own code in CodigoForn  ",
    })
    row = _rule_change_rows(tmp_path)[0]
    assert row["prose"] == "put the supplier's own code in CodigoForn"
    assert row["rationale"] == PATCH["rationale"]


def test_an_apply_without_prose_still_succeeds_and_records_empty(client, tmp_path):
    # Older clients send no prose; that must not fail the request.
    r = client.post("/admin/rules/apply", headers=_h(),
                    json={"proposal": PATCH, "base_version": 1})
    assert r.status_code == 200
    assert _rule_change_rows(tmp_path)[0]["prose"] == ""


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
    # Read back through the app's own accessor, which is what get_service()
    # rebuilds from — a store built by hand here would prove less.
    rule = appmod.get_rule_store().current()
    assert rule.lines.fields["supplier_code"].column == "CodigoForn"
    assert appmod._service is None      # reset; rebuilt lazily on next request
    # m1: the probe caches column lists per table, so it must be dropped too —
    # asserted here rather than relying on a later test to notice.
    assert appmod._schema_probe is None


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


def test_a_schema_outage_inside_drafting_is_503_not_a_422(client, monkeypatch):
    # I3: /admin/rules/draft must catch RuleDraftError and nothing wider.
    # SchemaUnavailable is a sibling RuntimeError, so widening that except to
    # RuntimeError would turn a database outage into "could not draft your
    # change" — a 422 blaming the admin's prose. The outage has to originate
    # inside draft() for the route's except to be the thing under test; the
    # current() call above it reads only the YAML on disk.
    def broken(sql, params):
        raise OSError("connection reset")
    monkeypatch.setattr(appmod, "_read", broken)

    class ProbingProposer:
        def draft(self, prose, rule, schema):
            schema.columns(rule.lines.table)        # raises SchemaUnavailable
            raise AssertionError("unreachable")
    monkeypatch.setattr(appmod, "get_proposer", lambda: ProbingProposer())

    appmod.reset_service()          # drop the cached probe
    r = client.post("/admin/rules/draft", headers=_h(), json={"prose": "x"})
    assert r.status_code == 503


def test_draft_stamps_the_real_base_version_over_the_models_guess(client):
    # m11: RuleChangeProposal.base_version is whatever Claude wrote. The 409
    # concurrency check in /apply compares it against the version on disk, so
    # it is only meaningful if the server stamps it.
    client.post("/admin/rules/apply", headers=_h(),
                json={"proposal": PATCH, "base_version": 1})   # disk is now v2
    assert PATCH["base_version"] == 1                          # model still says 1
    r = client.post("/admin/rules/draft", headers=_h(), json={"prose": "x"})
    assert r.status_code == 200
    assert r.json()["proposal"]["base_version"] == 2


def test_an_applied_change_survives_the_packaged_yaml_reverting(client, tmp_path):
    """The whole point of moving the document into the database.

    Render rebuilds the container from the image on every deploy, so the
    packaged YAML reappears exactly as it shipped. Restoring it here stands in
    for that: the applied mapping must still be the one in force.
    """
    client.post("/admin/rules/apply", headers=_h(),
                json={"proposal": PATCH, "base_version": 1})
    shutil.copy(_SRC, tmp_path / "purchase_invoice.yaml")   # the image comes back

    rule = appmod.get_rule_store().current()
    assert rule.version == 2
    assert rule.lines.fields["supplier_code"].column == "CodigoForn"


def test_an_unreadable_rule_table_is_503_not_a_silent_fallback(client, monkeypatch):
    """A missing rule table must not quietly fall back to the packaged YAML —
    that would write under a mapping the operator had already replaced."""
    @contextmanager
    def broken():
        raise RuntimeError("login failed for user")
        yield  # pragma: no cover

    monkeypatch.setattr(appmod, "get_bills_write_session", broken)
    r = client.get("/admin/rules/current", headers=_h())
    assert r.status_code == 503


def test_a_rule_table_outage_during_upload_is_503_not_a_bad_request(client, monkeypatch):
    """/bills/upload builds the service inside `except RuntimeError -> 400`, so
    an outage there would be reported to the operator as "your file is bad"."""
    @contextmanager
    def broken():
        raise RuntimeError("login failed for user")
        yield  # pragma: no cover

    monkeypatch.setattr(appmod, "get_bills_write_session", broken)
    appmod.reset_service()
    client.post("/bills/operator", json={"name": "alice"})
    r = client.post("/bills/upload",
                    files={"file": ("x.pdf", b"%PDF-1.4 fake", "application/pdf")})
    assert r.status_code == 503, f"got {r.status_code}: {r.text[:200]}"
