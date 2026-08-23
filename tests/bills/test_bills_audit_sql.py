import json

from db.bills_audit import TABLE, insert_audit


class FakeSession:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params))


ENTRY = {
    "ts": "2026-08-18T09:00:00.000Z", "kind": "bill_ingest", "operator": "alice",
    "proposal_id": "bill_abc123", "document_chave": 99, "supplier_chave": 7,
    "line_chaves": [1, 2], "created_supplier": False, "created_articles": [],
    "rule_doc": "purchase_invoice", "rule_version": "1.0", "status": "ok",
}


def test_insert_uses_the_audit_table_with_the_prefix():
    s = FakeSession()
    insert_audit(s, ENTRY, table_prefix="ForumSI.dbo.")
    sql, _ = s.calls[0]
    assert f"INSERT INTO ForumSI.dbo.{TABLE}" in sql


def test_insert_binds_every_column_as_a_parameter():
    s = FakeSession()
    insert_audit(s, ENTRY)
    sql, params = s.calls[0]
    # No entry value may be interpolated into the statement text.
    assert "alice" not in sql and "bill_abc123" not in sql
    assert params["Operator"] == "alice"
    assert params["ProposalId"] == "bill_abc123"
    assert params["DocumentChave"] == 99
    assert params["SupplierChave"] == 7
    assert params["Status"] == "ok"
    assert params["Ts"] == "2026-08-18T09:00:00.000Z"


def test_payload_carries_the_whole_entry_as_json():
    # Fields with no column of their own still survive, so adding one later
    # costs no migration.
    s = FakeSession()
    insert_audit(s, ENTRY)
    _, params = s.calls[0]
    assert json.loads(params["Payload"])["line_chaves"] == [1, 2]
    assert json.loads(params["Payload"])["created_supplier"] is False


def test_a_failure_entry_with_no_result_still_inserts():
    s = FakeSession()
    insert_audit(s, {"ts": "t", "operator": "bob", "proposal_id": "p",
                     "status": "error", "rule_doc": "d", "rule_version": "1"})
    _, params = s.calls[0]
    assert params["Status"] == "error"
    assert params["DocumentChave"] is None


def test_entry_keys_never_reach_the_statement_text():
    # The column list is a module constant; a hostile key must not become SQL.
    s = FakeSession()
    insert_audit(s, {**ENTRY, "Payload); DROP TABLE x--": "evil"})
    sql, _ = s.calls[0]
    assert "DROP TABLE" not in sql


def test_insert_defaults_to_the_connection_database():
    s = FakeSession()
    insert_audit(s, ENTRY)
    sql, _ = s.calls[0]
    assert f"INSERT INTO {TABLE}" in sql
    assert "ForumSI" not in sql
