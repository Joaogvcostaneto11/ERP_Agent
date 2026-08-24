import pytest

from logic.bills.rules.schema_probe import SchemaProbe

ROWS = {
    "Doc001": [
        {"COLUMN_NAME": "Chave", "DATA_TYPE": "int", "IS_NULLABLE": "NO"},
        {"COLUMN_NAME": "Iliquido", "DATA_TYPE": "decimal", "IS_NULLABLE": "YES"},
    ],
    "LinDoc001": [
        {"COLUMN_NAME": "Descricao", "DATA_TYPE": "varchar", "IS_NULLABLE": "YES"},
    ],
}


def _reader(calls=None):
    def read(sql, params):
        if calls is not None:
            calls.append(params["table"])
        return ROWS.get(params["table"], [])
    return read


def test_columns_are_keyed_case_insensitively_but_keep_schema_spelling():
    probe = SchemaProbe(_reader())
    cols = probe.columns("Doc001")
    assert set(cols) == {"chave", "iliquido"}
    assert cols["iliquido"].name == "Iliquido"
    assert cols["iliquido"].nullable is True
    assert cols["chave"].nullable is False


def test_resolve_returns_schema_spelling_for_any_casing():
    probe = SchemaProbe(_reader())
    assert probe.resolve("Doc001", "ILIQUIDO") == "Iliquido"
    assert probe.resolve("Doc001", "iliquido") == "Iliquido"


def test_resolve_returns_none_for_unknown_column_and_unknown_table():
    probe = SchemaProbe(_reader())
    assert probe.resolve("Doc001", "NoSuchColumn") is None
    assert probe.resolve("NoSuchTable", "Chave") is None


def test_results_are_cached_per_table_and_refresh_clears_them():
    calls = []
    probe = SchemaProbe(_reader(calls))
    probe.columns("Doc001")
    probe.columns("Doc001")
    assert calls == ["Doc001"]
    probe.refresh()
    probe.columns("Doc001")
    assert calls == ["Doc001", "Doc001"]


def test_a_database_failure_raises_schema_unavailable_rather_than_an_empty_map():
    # An empty map would silently mean "no such column" and reject every valid
    # proposal. Validation must fail loudly instead of degrading.
    from logic.bills.rules.schema_probe import SchemaUnavailable

    def broken(sql, params):
        raise OSError("connection reset")

    with pytest.raises(SchemaUnavailable):
        SchemaProbe(broken).columns("Doc001")


def test_a_failed_probe_is_not_cached():
    state = {"fail": True}

    def flaky(sql, params):
        if state["fail"]:
            raise OSError("down")
        return ROWS["Doc001"]

    probe = SchemaProbe(flaky)
    with pytest.raises(Exception):
        probe.columns("Doc001")
    state["fail"] = False
    assert probe.resolve("Doc001", "Chave") == "Chave"
