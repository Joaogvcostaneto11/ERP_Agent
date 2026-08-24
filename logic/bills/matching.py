from __future__ import annotations
from typing import Callable

from logic.bills.models import Bill, BillLine, Candidate, MatchResult
from logic.bills.rules.models import PurchaseInvoiceRule

Reader = Callable[[str, dict], list[dict]]


def _label(row: dict) -> str | None:
    """Name of the record a 'matched' result points at. A misread digit can land
    on a DIFFERENT existing supplier's NCont — both 502267583 and 502667583 are
    well-formed NIFs — so the operator has to see WHICH record was chosen, not
    just that something matched."""
    name = row.get("Nome")
    return None if name is None else str(name)


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
                return MatchResult(status="matched", chave=int(rows[0]["Chave"]),
                                   label=_label(rows[0]))
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
            return MatchResult(status="matched", chave=int(rows[0]["Chave"]),
                               label=_label(rows[0]))
        if len(rows) > 1:
            cands = [Candidate(chave=int(r["Chave"]), label=str(r["Nome"]), score=1.0)
                     for r in rows]
            return MatchResult(status="ambiguous", candidates=cands)
        return MatchResult(status="new", proposed_new=proposed_new)
