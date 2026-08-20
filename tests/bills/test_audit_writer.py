import json
from contextlib import contextmanager

import pytest

from logic.bills.audit_writer import BillAuditWriter
from logic.bills.models import MatchResult, WritePlan
from logic.chat.audit import AuditLog


class FakeFileAudit:
    def __init__(self):
        self.entries = []

    def append(self, entry):
        self.entries.append(entry)


class FakeSession:
    def __init__(self, fail=False):
        self.calls = []
        self._fail = fail

    def execute(self, statement, params=None):
        if self._fail:
            raise RuntimeError("db is down")
        self.calls.append((str(statement), params))


def _factory(session):
    @contextmanager
    def factory():
        yield session
    return factory


def _plan():
    return WritePlan(proposal_id="p1", supplier=MatchResult(status="matched", chave=7),
                     header={"Total": "123"}, lines=[], rule_doc="purchase_invoice",
                     rule_version=1)


RESULT = {"document_chave": 55, "supplier_chave": 7, "line_chaves": [1, 2],
          "created_supplier": False, "created_articles": []}


def test_insert_writes_the_row_on_the_session_it_is_given():
    file_audit, session = FakeFileAudit(), FakeSession()
    BillAuditWriter(file_audit).insert(session, operator="alice", plan=_plan(),
                                       result=RESULT, status="ok")
    assert len(session.calls) == 1
    _, params = session.calls[0]
    assert params["Operator"] == "alice"
    assert params["DocumentChave"] == 55


def test_insert_also_mirrors_to_the_file():
    file_audit, session = FakeFileAudit(), FakeSession()
    BillAuditWriter(file_audit).insert(session, operator="alice", plan=_plan(),
                                       result=RESULT, status="ok")
    assert file_audit.entries[0]["kind"] == "bill_ingest"
    assert file_audit.entries[0]["operator"] == "alice"


def test_insert_does_not_swallow_a_failed_audit_write():
    """The atomic guarantee: if the audit row cannot be written, the whole
    transaction must roll back rather than leave an unaudited document."""
    writer = BillAuditWriter(FakeFileAudit())
    with pytest.raises(RuntimeError):
        writer.insert(FakeSession(fail=True), operator="alice", plan=_plan(),
                      result=RESULT, status="ok")


def test_record_failure_opens_its_own_session():
    # The write transaction has already rolled back by the time a failure is
    # known, so the failure row cannot ride on it.
    file_audit, session = FakeFileAudit(), FakeSession()
    BillAuditWriter(file_audit, session_factory=_factory(session)).record_failure(
        operator="bob", plan=_plan(), result={}, status="error")
    assert len(session.calls) == 1
    assert session.calls[0][1]["Status"] == "error"
    assert file_audit.entries[0]["status"] == "error"


def test_record_failure_falls_back_to_the_file_when_the_db_is_also_down():
    # Usually the DB is down precisely because that is why the write failed;
    # masking the original error with this one would be worse than useless.
    file_audit = FakeFileAudit()
    writer = BillAuditWriter(file_audit, session_factory=_factory(FakeSession(fail=True)))
    writer.record_failure(operator="bob", plan=_plan(), result={}, status="error")
    assert file_audit.entries[0]["status"] == "error"


def test_record_failure_without_a_factory_still_mirrors_to_the_file():
    file_audit = FakeFileAudit()
    BillAuditWriter(file_audit).record_failure(operator="bob", plan=_plan(),
                                               result={}, status="error")
    assert file_audit.entries[0]["operator"] == "bob"


def test_entry_keeps_its_existing_shape(tmp_path):
    # Same keys the JSONL mirror carried before the database sink existed.
    log = AuditLog(tmp_path / "a.jsonl")
    BillAuditWriter(log).insert(FakeSession(), operator="alice", plan=_plan(),
                                result=RESULT, status="ok")
    entry = json.loads((tmp_path / "a.jsonl").read_text().splitlines()[0])
    assert set(entry) == {"ts", "kind", "operator", "proposal_id", "document_chave",
                          "supplier_chave", "line_chaves", "created_supplier",
                          "created_articles", "rule_doc", "rule_version", "status"}
    assert entry["rule_doc"] == "purchase_invoice" and entry["rule_version"] == 1
