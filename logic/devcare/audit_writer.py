# logic/devcare/audit_writer.py
from __future__ import annotations

from logic.chat.audit import AuditLog
from logic.devcare.errors import NormalizedChange


class AuditWriter:
    def __init__(self, audit: AuditLog) -> None:
        self._audit = audit

    def record(self, *, operator: str, change: NormalizedChange, rule_doc: str,
               rule_version: int, primary_key, before: dict | None,
               status: str) -> None:
        self._audit.append({
            "ts": AuditLog.now_iso(),
            "kind": "devcare_write",
            "operator": operator,
            "entity": change.entity,
            "operation": change.operation,
            "table": change.table,
            "primary_key": primary_key,
            "before": before,
            "after": change.columns if change.operation != "delete" else None,
            "rule_doc": rule_doc,
            "rule_version": rule_version,
            "status": status,
        })
