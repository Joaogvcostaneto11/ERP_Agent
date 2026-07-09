from __future__ import annotations

from logic.chat.audit import AuditLog
from logic.bills.models import WritePlan


class BillAuditWriter:
    def __init__(self, audit: AuditLog) -> None:
        self._audit = audit

    def record(self, *, operator: str, plan: WritePlan, result: dict,
               status: str) -> None:
        self._audit.append({
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
        })
