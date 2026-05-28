from __future__ import annotations
import concurrent.futures
import re
import time
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Callable


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


def _normalise(sql: str) -> str:
    s = _BLOCK_COMMENT.sub(" ", sql)
    s = _LINE_COMMENT.sub(" ", s)
    return s.strip()


def _strip_string_literals(s: str) -> str:
    # Removes single/double-quoted strings so semicolons inside them don't count.
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


from sqlalchemy import text  # noqa: E402


def _wrap(sql: str) -> str:
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
        start = time.monotonic()
        try:
            columns, rows = self._execute_with_timeout(wrapped, QUERY_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            return QueryError(code="timeout", message=f"query exceeded {QUERY_TIMEOUT_S}s")
        except Exception as e:
            return QueryError(code="db_error", message=str(e)[:500])
        duration_ms = int((time.monotonic() - start) * 1000)
        return QueryResult(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=len(rows) >= ROW_CAP,
            duration_ms=duration_ms,
        )

    def _execute_with_timeout(self, wrapped: str, timeout: float) -> tuple[list[str], list[list[Any]]]:
        def _work() -> tuple[list[str], list[list[Any]]]:
            with self._session_factory() as session:
                session.execute(text("SET LOCK_TIMEOUT 5000"))
                result = session.execute(text(wrapped))
                columns = list(result.keys())
                rows = [list(r) for r in result.fetchall()]
                return columns, rows

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_work)
            return fut.result(timeout=timeout)
