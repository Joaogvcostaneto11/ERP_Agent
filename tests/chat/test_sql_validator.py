from __future__ import annotations
import pytest

from logic.chat.sql_executor import QueryError, validate_sql


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "  SELECT 1  ",
    "select 1",
    "-- a comment\nSELECT 1",
    "/* block */ SELECT 1",
    "WITH cte AS (SELECT 1 AS x) SELECT * FROM cte",
    "SELECT a FROM t WHERE x = 'has ; inside'",
    "SELECT 1;",
])
def test_accepts_valid_select(sql):
    assert validate_sql(sql) is None


@pytest.mark.parametrize("sql,reason", [
    ("", "empty"),
    ("   ", "empty"),
    ("-- only comment", "empty"),
    ("DROP TABLE x", "forbidden"),
    ("DELETE FROM t", "forbidden"),
    ("UPDATE t SET x=1", "forbidden"),
    ("INSERT INTO t VALUES (1)", "forbidden"),
    ("SELECT 1; DROP TABLE x", "statement"),
    ("EXEC sp_help", "forbidden"),
    ("exec sp_help", "forbidden"),
    ("SELECT * INTO x FROM y", "forbidden"),
    ("WITH d AS (DELETE FROM t) SELECT * FROM d", "forbidden"),
    ("/* hide */ DROP TABLE x", "forbidden"),
    ("SELECT 1; SELECT 2", "statement"),
])
def test_rejects_invalid(sql, reason):
    result = validate_sql(sql)
    assert isinstance(result, QueryError), f"expected rejection for {sql!r}, got None"
    assert result.code == "rejected"


def test_trailing_semicolon_allowed():
    assert validate_sql("SELECT 1;") is None
