from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import text

from logic.bills.models import MatchResult, WritePlan
from logic.bills.rules.models import PurchaseInvoiceRule


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class BillWriteExecutor:
    """Writes a WritePlan as one transaction: (optional) new supplier + articles,
    then a draft Doc001 header and its LinDoc001 lines. All identifiers come from
    the rule document; all values are bound parameters."""

    def __init__(self, session_factory: Callable, *,
                 table_prefix: str = "ForumSI.dbo.",
                 now: Callable[[], str] = _now_iso, operator_key: int = 0) -> None:
        self._factory = session_factory
        self._p = table_prefix
        self._now = now
        self._operator_key = operator_key

    def _next_key(self, session, table: str) -> int:
        # Single-writer assumption, as in DevCare's WriteExecutor.
        return int(session.execute(
            text(f"SELECT COALESCE(MAX(Chave), 0) + 1 AS k FROM {self._p}{table}")
        ).scalar())

    def _insert(self, session, table: str, row: dict) -> None:
        cols = ", ".join(row)
        binds = ", ".join(f":{c}" for c in row)
        session.execute(text(f"INSERT INTO {self._p}{table} ({cols}) VALUES ({binds})"), row)

    def _resolve_entity(self, session, match: MatchResult, table: str,
                        defaults: dict) -> tuple[int, bool]:
        if match.status == "matched" and match.chave is not None:
            return match.chave, False
        if not match.confirmed or match.proposed_new is None:
            raise ValueError(f"new {table} record is not confirmed")
        pk = self._next_key(session, table)
        row = {"Chave": pk, **defaults, **match.proposed_new,
               "DC": self._now(), "OC": self._operator_key}
        self._insert(session, table, row)
        return pk, True

    def execute(self, plan: WritePlan, rule: PurchaseInvoiceRule) -> dict[str, Any]:
        with self._factory() as session:
            supplier_defaults = {"Tipo": 2, "Listar": 1}  # Tipo=2: supplier
            supplier_chave, created_supplier = self._resolve_entity(
                session, plan.supplier, rule.matching.supplier.table, supplier_defaults)

            tipo_doc = int(session.execute(
                text(f"SELECT Chave FROM {self._p}TiposDoc WHERE Codigo = :c"),
                {"c": rule.header.tipo_doc.code}).scalar())

            doc_pk = self._next_key(session, rule.header.table)
            header = {"Chave": doc_pk, "TipoDoc": tipo_doc,
                      rule.header.fields["supplier"].column: supplier_chave}
            header.update(rule.header.draft_defaults)
            created_at = rule.header.audit_columns.get("created_at")
            created_by = rule.header.audit_columns.get("created_by")
            if created_at:
                header[created_at] = self._now()
            if created_by:
                header[created_by] = self._operator_key
            header.update(plan.header)
            self._insert(session, rule.header.table, header)

            line_chaves: list[int] = []
            created_articles: list[int] = []
            for lp in plan.lines:
                art_chave, created = self._resolve_entity(
                    session, lp.article, rule.matching.article.table, {})
                if created:
                    created_articles.append(art_chave)
                line_pk = self._next_key(session, rule.lines.table)
                row = {"Chave": line_pk, rule.lines.parent_fk: doc_pk,
                       rule.lines.fields["article"].column: art_chave}
                row.update(lp.columns)
                self._insert(session, rule.lines.table, row)
                line_chaves.append(line_pk)

            return {"document_chave": doc_pk, "supplier_chave": supplier_chave,
                    "line_chaves": line_chaves, "created_supplier": created_supplier,
                    "created_articles": created_articles}
