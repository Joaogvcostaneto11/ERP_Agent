from __future__ import annotations
from contextlib import contextmanager
from typing import Any, Iterator

import pytest

from logic.chat.sql_executor import QueryError, QueryResult, ROW_CAP, SqlExecutor


class FakeResult:
    def __init__(self, columns: list[str], rows: list[list[Any]]) -> None:
        self._columns = columns
        self._rows = rows

    def keys(self) -> list[str]:
        return self._columns

    def fetchall(self) -> list[list[Any]]:
        return self._rows


class FakeSession:
    def __init__(self, *, rows: list[list[Any]], columns: list[str] | None = None,
                 raise_exc: Exception | None = None) -> None:
        self._rows = rows
        self._columns = columns or ["a", "b"]
        self._raise = raise_exc
        self.executed: list[str] = []

    def execute(self, stmt) -> FakeResult:
        sql = str(stmt) if not isinstance(stmt, str) else stmt
        self.executed.append(sql)
        if self._raise is not None:
            raise self._raise
        if "SET LOCK_TIMEOUT" in sql:
            return FakeResult([], [])
        return FakeResult(self._columns, self._rows)


def make_factory(session: FakeSession):
    @contextmanager
    def factory() -> Iterator[FakeSession]:
        yield session
    return factory


def test_run_query_happy_path():
    session = FakeSession(rows=[[1, 2], [3, 4]], columns=["x", "y"])
    ex = SqlExecutor(make_factory(session))
    result = ex.run_query("SELECT x, y FROM t")
    assert isinstance(result, QueryResult)
    assert result.columns == ["x", "y"]
    assert result.rows == [[1, 2], [3, 4]]
    assert result.row_count == 2
    assert result.truncated is False
    # the wrapped form was sent
    assert any("SELECT TOP (" in s for s in session.executed)


def test_run_query_truncates_at_row_cap():
    too_many = [[i] for i in range(ROW_CAP)]
    session = FakeSession(rows=too_many, columns=["i"])
    ex = SqlExecutor(make_factory(session))
    result = ex.run_query("SELECT i FROM t")
    assert isinstance(result, QueryResult)
    assert result.row_count == ROW_CAP
    assert result.truncated is True


def test_run_query_returns_error_on_rejection():
    session = FakeSession(rows=[])
    ex = SqlExecutor(make_factory(session))
    err = ex.run_query("DROP TABLE x")
    assert isinstance(err, QueryError)
    assert err.code == "rejected"
    assert session.executed == []  # never reached the DB


def test_run_query_wraps_db_error():
    session = FakeSession(rows=[], raise_exc=RuntimeError("connection lost"))
    ex = SqlExecutor(make_factory(session))
    err = ex.run_query("SELECT 1")
    assert isinstance(err, QueryError)
    assert err.code == "db_error"
    assert "connection lost" in err.message


def test_run_query_timeout(monkeypatch):
    import time as _time

    class SlowSession:
        executed: list[str] = []

        def execute(self, stmt):
            if "SET LOCK_TIMEOUT" in str(stmt):
                return FakeResult([], [])
            _time.sleep(2)
            return FakeResult(["x"], [[1]])

    @contextmanager
    def factory():
        yield SlowSession()

    # shorten timeout so the test finishes quickly
    monkeypatch.setattr("logic.chat.sql_executor.QUERY_TIMEOUT_S", 0.2)
    ex = SqlExecutor(factory)
    err = ex.run_query("SELECT 1")
    assert isinstance(err, QueryError)
    assert err.code == "timeout"


def test_run_query_with_cte_is_unwrapped():
    session = FakeSession(rows=[[1]], columns=["x"])
    ex = SqlExecutor(make_factory(session))
    result = ex.run_query("WITH cte AS (SELECT 1 AS x) SELECT * FROM cte")
    assert isinstance(result, QueryResult)
    # The CTE query was NOT wrapped in a derived table — there is no AS _capped
    assert not any("AS _capped" in s for s in session.executed)
    # The original CTE syntax is preserved in what we sent
    assert any("WITH cte AS" in s for s in session.executed)


def test_run_query_with_cte_truncates_python_side():
    too_many = [[i] for i in range(ROW_CAP + 5)]
    session = FakeSession(rows=too_many, columns=["i"])
    ex = SqlExecutor(make_factory(session))
    result = ex.run_query("WITH cte AS (SELECT i FROM t) SELECT i FROM cte")
    assert isinstance(result, QueryResult)
    assert result.row_count == ROW_CAP
    assert result.truncated is True


class SmartSession:
    """A FakeSession that distinguishes the failing user query from the
    follow-up INFORMATION_SCHEMA.COLUMNS lookup."""
    def __init__(self, fail_message: str, columns_returned: list[str]) -> None:
        self._fail = fail_message
        self._columns = columns_returned
        self.executed: list[str] = []

    def execute(self, stmt, params=None) -> FakeResult:
        sql = str(stmt) if not isinstance(stmt, str) else stmt
        self.executed.append(sql)
        if "SET LOCK_TIMEOUT" in sql:
            return FakeResult([], [])
        if "INFORMATION_SCHEMA.COLUMNS" in sql:
            return FakeResult(["COLUMN_NAME"], [[c] for c in self._columns])
        raise RuntimeError(self._fail)


def test_invalid_column_error_is_enriched_with_actual_columns():
    session = SmartSession(
        fail_message="(pyodbc.ProgrammingError) ('42S22', \"[42S22] [Microsoft][ODBC Driver 18 for SQL Server]"
                     "[SQL Server]Invalid column name 'Descricao'. (207)\")",
        columns_returned=["Chave", "Codigo", "Nome"],
    )
    ex = SqlExecutor(make_factory(session))
    err = ex.run_query("SELECT TOP 5 Descricao FROM DOClinic.dbo.TiposDoc")
    assert isinstance(err, QueryError)
    assert err.code == "db_error"
    assert "Invalid column name" in err.message
    assert "Actual columns" in err.message
    assert "DOClinic.dbo.TiposDoc" in err.message
    assert "Chave" in err.message and "Nome" in err.message


def test_invalid_object_error_is_enriched():
    session = SmartSession(
        fail_message="Invalid object name 'DOClinic.dbo.WrongName'.",
        columns_returned=["x", "y"],
    )
    ex = SqlExecutor(make_factory(session))
    err = ex.run_query("SELECT * FROM DOClinic.dbo.WrongName")
    assert isinstance(err, QueryError)
    assert "Actual columns" in err.message


def test_non_schema_errors_are_not_enriched():
    """Connection failures or syntax errors shouldn't trigger a column lookup."""
    session = FakeSession(rows=[], raise_exc=RuntimeError("connection lost"))
    ex = SqlExecutor(make_factory(session))
    err = ex.run_query("SELECT 1 FROM t")
    assert isinstance(err, QueryError)
    assert "Actual columns" not in err.message


def test_enrichment_quietly_skips_when_lookup_fails():
    """A failed lookup must not mask the original error."""
    class FailingLookupSession:
        def __init__(self):
            self.executed = []
            self._first_call = True

        def execute(self, stmt, params=None):
            self.executed.append(str(stmt))
            if "SET LOCK_TIMEOUT" in str(stmt):
                return FakeResult([], [])
            if self._first_call:
                self._first_call = False
                raise RuntimeError("Invalid column name 'X'.")
            raise RuntimeError("schema lookup failed too")

    ex = SqlExecutor(make_factory(FailingLookupSession()))
    err = ex.run_query("SELECT X FROM dbo.T")
    assert isinstance(err, QueryError)
    assert "Invalid column name" in err.message
    # No "Actual columns" header because lookup failed
    assert "Actual columns" not in err.message


def test_enrichment_rejects_unsafe_database_identifier():
    """Reject malformed db identifiers to avoid SQL-injection via FROM clause."""
    session = SmartSession(
        fail_message="Invalid column name 'X'.",
        columns_returned=["a", "b"],
    )
    ex = SqlExecutor(make_factory(session))
    # Backticked database name (unsafe identifier) should skip enrichment
    err = ex.run_query("SELECT X FROM `bad name`.dbo.T")
    assert isinstance(err, QueryError)
    # The regex doesn't match the unsafe form anyway, so the table ref isn't
    # extracted — no enrichment.
    assert "Actual columns" not in err.message
