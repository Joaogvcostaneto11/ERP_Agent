from __future__ import annotations
import concurrent.futures
import re
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy import text


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    duration_ms: int


@dataclass
class QueryError:
    code: str  # "rejected" | "timeout" | "db_error"
    message: str


ROW_CAP = 1000
QUERY_TIMEOUT_S = 30

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_FORBIDDEN = re.compile(
    r"(?i)\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXEC|EXECUTE|INTO)\b"
    r"|\b(xp_|sp_)\w*",
)

# Long-lived pool so we don't pay creation cost per query and don't block on
# __exit__ when a worker is still running after a timeout.
_QUERY_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="sql_query"
)


def _normalise(sql: str) -> str:
    s = _BLOCK_COMMENT.sub(" ", sql)
    s = _LINE_COMMENT.sub(" ", s)
    return s.strip()


def _strip_string_literals(s: str) -> str:
    return re.sub(r"'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\"", "", s)


def validate_sql(sql: str) -> QueryError | None:
    normalised = _normalise(sql)
    if not normalised:
        return QueryError(code="rejected", message="empty SQL")
    body = _strip_string_literals(normalised).rstrip(";")
    if ";" in body:
        return QueryError(code="rejected", message="only one statement allowed")
    if not re.match(r"^\s*(SELECT|WITH)\b", normalised, re.IGNORECASE):
        return QueryError(code="rejected", message="only SELECT or WITH allowed")
    m = _FORBIDDEN.search(normalised)
    if m:
        return QueryError(code="rejected", message=f"forbidden keyword: {m.group(0)}")
    return None


def _wrap(sql: str) -> str | None:
    """Return a TOP-capped SELECT, or None for CTE (WITH) queries.

    CTEs cannot appear inside a derived-table subquery in SQL Server, so they
    are sent as-is and capped Python-side in run_query.
    """
    normalised = _normalise(sql)
    if re.match(r"^\s*WITH\b", normalised, re.IGNORECASE):
        return None
    body = sql.rstrip().rstrip(";")
    return f"SELECT TOP ({ROW_CAP}) * FROM (\n{body}\n) AS _capped"


class SqlExecutor:
    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Any]],
    ) -> None:
        self._session_factory = session_factory

    def run_query(self, sql: str) -> QueryResult | QueryError:
        err = validate_sql(sql)
        if err is not None:
            return err
        wrapped = _wrap(sql)
        is_cte = wrapped is None
        to_execute = sql.rstrip().rstrip(";") if is_cte else wrapped
        start = time.monotonic()
        try:
            columns, rows = self._execute_with_timeout(to_execute, QUERY_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            return QueryError(code="timeout", message=f"query exceeded {QUERY_TIMEOUT_S}s")
        except Exception as e:
            return QueryError(code="db_error", message=str(e)[:500])
        duration_ms = int((time.monotonic() - start) * 1000)
        if is_cte:
            truncated = len(rows) > ROW_CAP
            rows = rows[:ROW_CAP]
        else:
            truncated = len(rows) >= ROW_CAP
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            duration_ms=duration_ms,
        )

    def _execute_with_timeout(self, sql: str, timeout: float) -> tuple[list[str], list[list[Any]]]:
        def _work() -> tuple[list[str], list[list[Any]]]:
            with self._session_factory() as session:
                session.execute(text("SET LOCK_TIMEOUT 5000"))
                result = session.execute(text(sql))
                return list(result.keys()), [list(r) for r in result.fetchall()]

        return _QUERY_POOL.submit(_work).result(timeout=timeout)
