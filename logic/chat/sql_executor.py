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


class _Unterminated(Exception):
    """A quoted run or a block comment is never closed."""


# Closing delimiter per quoting construct. In all three a doubled closer is an
# escaped closer rather than the end of the run: '' inside '...', "" inside
# "..." and ]] inside [...].
_CLOSERS = {"'": "'", '"': '"', "[": "]"}


def _code_only(sql: str) -> str:
    """``sql`` with every comment and every quoted run replaced by one space.

    This walks the statement the way SQL Server's lexer does rather than
    pattern-matching it. A regex cannot tell a comment from the characters
    ``--`` sitting inside a string literal or a [bracketed] identifier, and
    reading the latter as a comment hides the whole rest of the statement —
    a second statement after a semicolon included — from every check that
    follows, while the server still executes it in full.

    Raises _Unterminated when a quote or block comment is never closed: at that
    point our reading of the statement and the server's have already diverged,
    so nothing derived from it can be trusted.
    """
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        closer = _CLOSERS.get(ch)
        if closer is not None:
            i += 1
            while True:
                j = sql.find(closer, i)
                if j < 0:
                    raise _Unterminated(f"unterminated {ch} quoting")
                if sql[j + 1:j + 2] == closer:
                    i = j + 2           # escaped closer: the run continues
                    continue
                i = j + 1
                break
            out.append(" ")
        elif sql.startswith("--", i):
            nl = sql.find("\n", i)
            i = n if nl < 0 else nl     # the newline itself survives as space
            out.append(" ")
        elif sql.startswith("/*", i):
            i += 2
            depth = 1
            while depth:
                # SQL Server nests block comments, so the first */ does not
                # necessarily close the one we are inside.
                opened = sql.find("/*", i)
                closed = sql.find("*/", i)
                if closed < 0:
                    raise _Unterminated("unterminated /* comment")
                if 0 <= opened < closed:
                    depth += 1
                    i = opened + 2
                else:
                    depth -= 1
                    i = closed + 2
            out.append(" ")
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def validate_sql(sql: str) -> QueryError | None:
    try:
        code = _code_only(sql).strip()
    except _Unterminated as e:
        return QueryError(code="rejected", message=str(e))
    if not code:
        return QueryError(code="rejected", message="empty SQL")
    if ";" in code.rstrip(";"):
        return QueryError(code="rejected", message="only one statement allowed")
    if not re.match(r"^\s*(SELECT|WITH)\b", code, re.IGNORECASE):
        return QueryError(code="rejected", message="only SELECT or WITH allowed")
    m = _FORBIDDEN.search(code)
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

    Only ever called on SQL that validate_sql has already accepted, so
    _code_only cannot raise here.
    """
    code = _code_only(sql)
    if re.match(r"^\s*WITH\b", code, re.IGNORECASE):
        return None
    if re.search(r"\bORDER\s+BY\b", code, re.IGNORECASE):
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
