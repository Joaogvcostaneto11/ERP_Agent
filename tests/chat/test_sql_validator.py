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


# A `--` or `/*` inside a string literal or a [bracketed] identifier is data to
# SQL Server, not a comment. Stripping it as a comment hides everything after it
# from validation while the server still executes it. Each case below carries a
# second statement behind such a sequence.
@pytest.mark.parametrize("sql", [
    "WITH c AS (SELECT 1 AS a) SELECT '--' FROM c; DELETE FROM Employees",
    "SELECT '--' AS a; DROP TABLE Employees",
    "SELECT '/*' AS a; DELETE FROM Employees",
    'SELECT "--" AS a; DELETE FROM Employees',
    "SELECT [a--b] FROM t; DELETE FROM Employees",
])
def test_rejects_statement_hidden_behind_a_quoted_comment_sequence(sql):
    result = validate_sql(sql)
    assert isinstance(result, QueryError), f"expected rejection for {sql!r}, got None"
    assert result.code == "rejected"


# An unterminated quote or block comment means our reading of the statement and
# the server's have already diverged, so nothing downstream can be trusted.
@pytest.mark.parametrize("sql", [
    "SELECT 'unterminated",
    'SELECT "unterminated',
    "SELECT [unterminated",
    "SELECT 1 /* unterminated",
])
def test_rejects_unterminated_quoting(sql):
    result = validate_sql(sql)
    assert isinstance(result, QueryError), f"expected rejection for {sql!r}, got None"
    assert result.code == "rejected"


@pytest.mark.parametrize("sql", [
    "SELECT a FROM t WHERE note = 'contains -- two dashes'",
    "SELECT a FROM t WHERE note = 'contains /* a block open'",
    "SELECT [odd--column] FROM t",
    "SELECT 'it''s escaped' FROM t",
])
def test_accepts_comment_sequences_that_are_only_data(sql):
    assert validate_sql(sql) is None
