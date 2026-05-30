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
ENRICH_TIMEOUT_S = 5
ENRICH_MAX_TABLES = 3
ENRICH_MAX_COLUMNS = 200
ERROR_MESSAGE_MAX = 1500  # raised from 500 to make room for column hints

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_FORBIDDEN = re.compile(
    r"(?i)\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXEC|EXECUTE|INTO)\b"
    r"|\b(xp_|sp_)\w*",
)

# Captures the table reference after FROM/JOIN, supporting up to a 3-part name
# (database.schema.table). Square-bracket-quoted identifiers are not handled.
_TABLE_REF_RE = re.compile(
    r"(?i)\b(?:FROM|JOIN)\s+([A-Za-z_]\w*(?:\.[A-Za-z_]\w*){0,2})"
)
_SAFE_IDENT_RE = re.compile(r"^[A-Za-z_]\w*$")

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
    """Return a TOP-capped SELECT, or None when the query must be sent as-is.

    SQL Server forbids two constructs inside a derived-table subquery (which is
    what our wrapper creates):
      * CTE (WITH) queries — they can't appear inside a subquery.
      * ORDER BY without a matching TOP/OFFSET/FOR XML — invalid in subqueries.
    In both cases we send the user's SQL unwrapped and enforce the row cap
    Python-side in ``run_query``.
    """
    normalised = _normalise(sql)
    if re.match(r"^\s*WITH\b", normalised, re.IGNORECASE):
        return None
    if re.search(r"\bORDER\s+BY\b", normalised, re.IGNORECASE):
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
        is_unwrapped = wrapped is None
        to_execute = sql.rstrip().rstrip(";") if is_unwrapped else wrapped
        start = time.monotonic()
        try:
            columns, rows = self._execute_with_timeout(to_execute, QUERY_TIMEOUT_S)
        except concurrent.futures.TimeoutError:
            return QueryError(code="timeout", message=f"query exceeded {QUERY_TIMEOUT_S}s")
        except Exception as e:
            message = self._enrich_db_error(sql, str(e))
            return QueryError(code="db_error", message=message[:ERROR_MESSAGE_MAX])
        duration_ms = int((time.monotonic() - start) * 1000)
        if is_unwrapped:
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

    def _enrich_db_error(self, sql: str, message: str) -> str:
        """When the DB rejects a column or object name, look up the real schema
        of the referenced tables and append it to the error message so the
        agent can self-correct on the next attempt without guessing.
        """
        if "Invalid column name" not in message and "Invalid object name" not in message:
            return message
        refs: list[str] = []
        seen: set[str] = set()
        for ref in _TABLE_REF_RE.findall(sql):
            key = ref.lower()
            if key not in seen:
                seen.add(key)
                refs.append(ref)
        hints: list[str] = []
        for ref in refs[:ENRICH_MAX_TABLES]:
            cols = self._lookup_columns(ref)
            if cols:
                hints.append(f"  {ref}: {', '.join(cols)}")
        if not hints:
            return message
        return (
            message
            + "\n\nActual columns in the referenced tables (use these on retry):\n"
            + "\n".join(hints)
        )

    def _lookup_columns(self, table_ref: str) -> list[str]:
        """Run an INFORMATION_SCHEMA.COLUMNS query for ``table_ref`` (an up to
        3-part name). Returns [] on any failure — enrichment is best-effort.
        """
        parts = table_ref.split(".")
        if len(parts) == 1:
            db, schema, table = None, "dbo", parts[0]
        elif len(parts) == 2:
            db, schema, table = None, parts[0], parts[1]
        elif len(parts) == 3:
            db, schema, table = parts[0], parts[1], parts[2]
        else:
            return []
        if db is not None and not _SAFE_IDENT_RE.match(db):
            return []
        qualified = (
            f"{db}.INFORMATION_SCHEMA.COLUMNS" if db else "INFORMATION_SCHEMA.COLUMNS"
        )
        query = (
            f"SELECT TOP ({ENRICH_MAX_COLUMNS}) COLUMN_NAME FROM {qualified} "
            "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :tbl ORDER BY ORDINAL_POSITION"
        )

        def _work() -> list[str]:
            with self._session_factory() as session:
                result = session.execute(text(query), {"schema": schema, "tbl": table})
                return [r[0] for r in result.fetchall()]

        try:
            return _QUERY_POOL.submit(_work).result(timeout=ENRICH_TIMEOUT_S)
        except Exception:
            return []
