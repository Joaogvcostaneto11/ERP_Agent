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
    the rule document; all values are bound parameters. Caller-supplied column
    dicts are whitelisted against the rule's declared columns, and protected
    (computed) columns are applied last so a caller cannot override them."""

    def __init__(self, session_factory: Callable, *,
                 table_prefix: str = "ForumSI.dbo.",
                 now: Callable[[], str] = _now_iso, operator_key: int = 0) -> None:
        self._factory = session_factory
        self._p = table_prefix
        self._now = now
        self._operator_key = operator_key

    @staticmethod
    def _check_columns(allowed: set[str], columns: dict) -> None:
        for key in columns:
            if key not in allowed:
                raise ValueError(f"column {key!r} is not a declared writable field")

    def _next_key(self, session, table: str) -> int:
        # Single-writer assumption, as in DevCare's WriteExecutor. Re-queried per
        # insert so same-transaction prior inserts are visible (read-your-writes).
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
        if match.status == "new" and match.confirmed and match.proposed_new is not None:
            pk = self._next_key(session, table)
            row = {"Chave": pk, **defaults, **match.proposed_new,
                   "DC": self._now(), "OC": self._operator_key}
            self._insert(session, table, row)
            return pk, True
        raise ValueError(
            f"cannot write {table}: match not resolvable "
            f"(status={match.status!r}, confirmed={match.confirmed})")

    def execute(self, plan: WritePlan, rule: PurchaseInvoiceRule) -> dict[str, Any]:
        # Whitelist caller columns against the rule's declared fields BEFORE any write.
        allowed_header = {fr.column for fr in rule.header.fields.values()}
        allowed_line = {fr.column for fr in rule.lines.fields.values()}
        self._check_columns(allowed_header, plan.header)
        for lp in plan.lines:
            self._check_columns(allowed_line, lp.columns)

        with self._factory() as session:
            supplier_chave, created_supplier = self._resolve_entity(
                session, plan.supplier, rule.matching.supplier.table,
                dict(rule.matching.supplier.create_defaults))

            tipo_doc = int(session.execute(
                text(f"SELECT Chave FROM {self._p}TiposDoc WHERE Codigo = :c"),
                {"c": rule.header.tipo_doc.code}).scalar())

            doc_pk = self._next_key(session, rule.header.table)
            header = dict(plan.header)                        # caller columns first
            header["Chave"] = doc_pk                           # protected/computed last
            header["TipoDoc"] = tipo_doc
            header[rule.header.fields["supplier"].column] = supplier_chave
            header.update(rule.header.draft_defaults)
            created_at = rule.header.audit_columns.get("created_at")
            created_by = rule.header.audit_columns.get("created_by")
            if created_at:
                header[created_at] = self._now()
            if created_by:
                header[created_by] = self._operator_key
            self._insert(session, rule.header.table, header)

            line_chaves: list[int] = []
            created_articles: list[int] = []
            for lp in plan.lines:
                art_chave, created = self._resolve_entity(
                    session, lp.article, rule.matching.article.table,
                    dict(rule.matching.article.create_defaults))
                if created:
                    created_articles.append(art_chave)
                line_pk = self._next_key(session, rule.lines.table)
                row = dict(lp.columns)                         # caller columns first
                row["Chave"] = line_pk                          # protected/computed last
                row[rule.lines.parent_fk] = doc_pk
                row[rule.lines.fields["article"].column] = art_chave
                self._insert(session, rule.lines.table, row)
                line_chaves.append(line_pk)

            return {"document_chave": doc_pk, "supplier_chave": supplier_chave,
                    "line_chaves": line_chaves, "created_supplier": created_supplier,
                    "created_articles": created_articles}
