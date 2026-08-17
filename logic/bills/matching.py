from __future__ import annotations
from typing import Callable

from logic.bills.models import Bill, BillLine, Candidate, MatchResult
from logic.bills.rules.models import PurchaseInvoiceRule

Reader = Callable[[str, dict], list[dict]]


def supplier_proposal(bill: Bill) -> dict:
    """Columns for a supplier the operator asks us to create. Single source of
    truth: the service re-derives this from the EDITED bill at stage time, so a
    NIF the operator corrected on screen is the one that reaches Entidades.
    Keys must stay within matching.supplier.create_columns in the rule doc —
    the executor whitelists against it."""
    return {"Nome": bill.supplier_name, "NCont": bill.supplier_tax_id}


def line_proposal(line: BillLine) -> dict:
    """As supplier_proposal, for a new article. Keys must stay within
    matching.article.create_columns."""
    return {"Nome": line.description}


class Matcher:
    """Read-only supplier/article matching. Never writes; 'new' means the
    service will offer to create the record on the operator's confirmation."""

    def __init__(self, reader: Reader, rule: PurchaseInvoiceRule, *,
                 table_prefix: str = "") -> None:
        self._read = reader
        self._rule = rule
        self._p = table_prefix

    def match_supplier(self, bill: Bill) -> MatchResult:
        ent = self._rule.matching.supplier.table
        if bill.supplier_tax_id:
            rows = self._read(
                f"SELECT Chave, Nome, NCont FROM {self._p}{ent} WHERE NCont = :tax_id",
                {"tax_id": bill.supplier_tax_id})
            if len(rows) == 1:
                return MatchResult(status="matched", chave=int(rows[0]["Chave"]))
        rows = self._read(
            f"SELECT Chave, Nome FROM {self._p}{ent} WHERE LOWER(Nome) LIKE :name",
            {"name": f"%{bill.supplier_name.lower()}%"})
        return self._resolve(rows, supplier_proposal(bill))

    def match_line(self, line: BillLine) -> MatchResult:
        art = self._rule.matching.article.table
        rows = self._read(
            f"SELECT Chave, Nome FROM {self._p}{art} WHERE LOWER(Nome) LIKE :name",
            {"name": f"%{line.description.lower()}%"})
        return self._resolve(rows, line_proposal(line))

    @staticmethod
    def _resolve(rows: list[dict], proposed_new: dict) -> MatchResult:
        if len(rows) == 1:
            return MatchResult(status="matched", chave=int(rows[0]["Chave"]))
        if len(rows) > 1:
            cands = [Candidate(chave=int(r["Chave"]), label=str(r["Nome"]), score=1.0)
                     for r in rows]
            return MatchResult(status="ambiguous", candidates=cands)
        return MatchResult(status="new", proposed_new=proposed_new)
