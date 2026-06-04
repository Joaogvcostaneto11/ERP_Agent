# logic/devcare/write_executor.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

from logic.devcare.errors import NormalizedChange
from logic.devcare.rules.models import EntityRule


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class WriteExecutor:
    """Executes a NormalizedChange in one transaction. Identifiers come only
    from the EntityRule (registry), values are always bound parameters.

    ``table_prefix`` is "DevCare.dbo." in production and "" for SQLite tests.
    """

    def __init__(self, session_factory: Callable, *, table_prefix: str = "DevCare.dbo.",
                 now: Callable[[], str] = _now_iso, operator_key: int = 0) -> None:
        self._factory = session_factory
        self._prefix = table_prefix
        self._now = now
        self._operator_key = operator_key

    def execute(self, rule: EntityRule, change: NormalizedChange) -> Any:
        qtable = f"{self._prefix}{rule.table}"
        with self._factory() as session:
            if change.operation == "create":
                return self._create(session, rule, change, qtable)
            if change.operation == "update":
                self._update(session, rule, change, qtable)
                return change.target_pk
            if change.operation == "delete":
                self._delete(session, rule, change, qtable)
                return change.target_pk
            raise ValueError(f"unknown operation {change.operation!r}")

    def _next_key(self, session, rule, qtable) -> int:
        cur = session.execute(
            text(f"SELECT COALESCE(MAX({rule.primary_key}), 0) + 1 AS k FROM {qtable}")
        ).scalar()
        return int(cur)

    def _create(self, session, rule, change, qtable) -> int:
        pk = self._next_key(session, rule, qtable)
        row: dict = {rule.primary_key: pk}
        row.update(rule.create_defaults)
        if rule.soft_delete is not None:
            row[rule.soft_delete.column] = rule.soft_delete.active_value
        if rule.audit_columns.created_at:
            row[rule.audit_columns.created_at] = self._now()
        if rule.audit_columns.created_by:
            row[rule.audit_columns.created_by] = self._operator_key
        row.update(change.columns)
        cols = ", ".join(row)
        binds = ", ".join(f":{c}" for c in row)
        session.execute(text(f"INSERT INTO {qtable} ({cols}) VALUES ({binds})"), row)
        return pk

    def _update(self, session, rule, change, qtable) -> None:
        sets = dict(change.columns)
        if rule.audit_columns.updated_at:
            sets[rule.audit_columns.updated_at] = self._now()
        if rule.audit_columns.updated_by:
            sets[rule.audit_columns.updated_by] = self._operator_key
        assignments = ", ".join(f"{c} = :{c}" for c in sets)
        params = dict(sets)
        params["_pk"] = change.target_pk
        session.execute(
            text(f"UPDATE {qtable} SET {assignments} WHERE {rule.primary_key} = :_pk"),
            params,
        )

    def _delete(self, session, rule, change, qtable) -> None:
        if rule.soft_delete is None:
            session.execute(
                text(f"DELETE FROM {qtable} WHERE {rule.primary_key} = :_pk"),
                {"_pk": change.target_pk},
            )
            return
        sets = {rule.soft_delete.column: rule.soft_delete.deleted_value}
        if rule.audit_columns.updated_at:
            sets[rule.audit_columns.updated_at] = self._now()
        if rule.audit_columns.updated_by:
            sets[rule.audit_columns.updated_by] = self._operator_key
        assignments = ", ".join(f"{c} = :{c}" for c in sets)
        params = dict(sets)
        params["_pk"] = change.target_pk
        session.execute(
            text(f"UPDATE {qtable} SET {assignments} WHERE {rule.primary_key} = :_pk"),
            params,
        )
