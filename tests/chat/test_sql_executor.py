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
