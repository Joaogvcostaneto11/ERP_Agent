from __future__ import annotations

import logging
from typing import Any, Callable

from db.bills_audit import insert_audit
from logic.bills.models import WritePlan
from logic.chat.audit import AuditLog

_log = logging.getLogger(__name__)


class BillAuditWriter:
    """Builds the audit entry and puts it where it survives a restart.

    The database row is the record of truth. The JSONL file is a mirror: an
    on-box diagnostic, and the surviving copy if the INSERT itself fails.
    Render's disk is ephemeral, so the file alone would not satisfy the
    audit-trail requirement."""

    def __init__(self, audit: AuditLog, *, session_factory: Callable | None = None,
                 table_prefix: str = "") -> None:
        self._audit = audit
        self._factory = session_factory
        self._prefix = table_prefix

    def _entry(self, *, operator: str, plan: WritePlan, result: dict,
               status: str) -> dict[str, Any]:
        return {
            "ts": AuditLog.now_iso(),
            "kind": "bill_ingest",
            "operator": operator,
            "proposal_id": plan.proposal_id,
            "document_chave": result.get("document_chave"),
            "supplier_chave": result.get("supplier_chave"),
            "line_chaves": result.get("line_chaves"),
            "created_supplier": result.get("created_supplier"),
            "created_articles": result.get("created_articles"),
            "rule_doc": plan.rule_doc,
            "rule_version": plan.rule_version,
            "status": status,
        }

    def insert(self, session, *, operator: str, plan: WritePlan, result: dict,
               status: str) -> None:
        """Write the audit row on the caller's session — inside the document's
        own transaction.

        Deliberately does NOT swallow: if the audit row cannot be written, the
        transaction rolls back and no unaudited document is left behind."""
        entry = self._entry(operator=operator, plan=plan, result=result, status=status)
        insert_audit(session, entry, table_prefix=self._prefix)
        self._audit.append(entry)

    def record_failure(self, *, operator: str, plan: WritePlan, result: dict,
                       status: str) -> None:
        """Audit a write that failed. Its transaction has already rolled back,
        so this opens its own session — best-effort, because the database is
        often down precisely because that is why the write failed, and masking
        the original error with this one helps nobody."""
        entry = self._entry(operator=operator, plan=plan, result=result, status=status)
        if self._factory is not None:
            try:
                with self._factory() as session:
                    insert_audit(session, entry, table_prefix=self._prefix)
            except Exception:
                _log.exception("audit row insert failed; entry survives in the file mirror")
        self._audit.append(entry)
