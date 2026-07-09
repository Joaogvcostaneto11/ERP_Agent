from __future__ import annotations
import uuid
from typing import Any, Callable

from logic.bills.extract.parser import BillParser
from logic.bills.matching import Matcher
from logic.bills.models import (Bill, BillLine, BillProposal, LinePlan,
                                MatchResult, WritePlan, arithmetic_warnings)
from logic.bills.pending import PendingProposalStore
from logic.bills.rules.models import PurchaseInvoiceRule


class BillService:
    def __init__(self, *, anthropic_client: Any, ocr_fn: Callable[[bytes], list],
                 rule: PurchaseInvoiceRule, reader: Callable, pending: PendingProposalStore,
                 executor, audit, model: str, table_prefix: str = "") -> None:
        self._ocr = ocr_fn
        self._rule = rule
        self._reader = reader
        self._pending = pending
        self._executor = executor
        self._audit = audit
        self._prefix = table_prefix
        self._parser = BillParser(anthropic_client, model, rule)
        self._matcher = Matcher(reader, rule, table_prefix=table_prefix)

    # ---- upload -----------------------------------------------------------
    def upload(self, pdf_bytes: bytes) -> BillProposal:
        pages = self._ocr(pdf_bytes)
        bill = self._parser.parse(pages)
        supplier_match = self._matcher.match_supplier(bill)
        line_matches = [self._matcher.match_line(ln) for ln in bill.lines]
        proposal = BillProposal(
            proposal_id="bill_" + uuid.uuid4().hex[:12], bill=bill,
            supplier_match=supplier_match, line_matches=line_matches,
            warnings=arithmetic_warnings(bill))
        self._pending.put(proposal.proposal_id, proposal)
        return proposal

    # ---- stage ------------------------------------------------------------
    def _bill_value(self, bill: Bill, source: str):
        # getattr default keeps mapped-but-unextracted fields (e.g. notes) safe.
        return getattr(bill, source.split(".", 1)[1], None)

    def _line_value(self, line: BillLine, source: str):
        return getattr(line, source.split(".", 1)[1], None)

    def _build_header(self, bill: Bill) -> tuple[dict, list[dict]]:
        cols, violations = {}, []
        for name, fr in self._rule.header.fields.items():
            if fr.source in ("supplier.match",):
                continue  # resolved by executor
            val = self._bill_value(bill, fr.source)
            if fr.required and (val is None or val == ""):
                violations.append({"field": name, "message": f"{name} is required"})
                continue
            if val is not None:
                cols[fr.column] = str(val)
        return cols, violations

    def _build_line(self, line: BillLine) -> tuple[dict, list[dict]]:
        cols, violations = {}, []
        for name, fr in self._rule.lines.fields.items():
            if fr.source == "line.match":
                continue
            val = self._line_value(line, fr.source)
            if fr.required and (val is None or val == ""):
                violations.append({"field": name, "message": f"line {name} is required"})
                continue
            if val is not None:
                cols[fr.column] = str(val)
        return cols, violations

    def stage(self, proposal_id: str, edited: dict) -> dict:
        proposal = BillProposal.model_validate(edited)
        self._pending.put(proposal_id, proposal)  # keep latest edits
        violations: list[dict] = []

        # confirmation gate for new records
        if proposal.supplier_match.status == "new" and not proposal.supplier_match.confirmed:
            violations.append({"field": "supplier",
                               "message": "new supplier must be confirmed before writing"})
        for i, lm in enumerate(proposal.line_matches):
            if lm.status == "new" and not lm.confirmed:
                violations.append({"field": f"line[{i}]",
                                   "message": "new article must be confirmed before writing"})
            if lm.status == "ambiguous" and lm.chave is None:
                violations.append({"field": f"line[{i}]",
                                   "message": "pick a candidate article before writing"})
        if proposal.supplier_match.status == "ambiguous" and proposal.supplier_match.chave is None:
            violations.append({"field": "supplier",
                               "message": "pick a candidate supplier before writing"})

        header, hv = self._build_header(proposal.bill)
        violations += hv
        line_plans: list[LinePlan] = []
        for i, (line, lm) in enumerate(zip(proposal.bill.lines, proposal.line_matches)):
            cols, lv = self._build_line(line)
            violations += lv
            line_plans.append(LinePlan(article=lm, columns=cols))

        if violations:
            return {"ok": False, "violations": violations}

        plan = WritePlan(proposal_id=proposal_id, supplier=proposal.supplier_match,
                         header=header, lines=line_plans,
                         rule_doc=self._rule.document, rule_version=self._rule.version)
        self._pending.put(proposal_id + ":plan", plan)
        return {"ok": True, "write_plan": plan.model_dump(mode="json"),
                "warnings": self._duplicate_warnings(proposal.bill) + proposal.warnings}

    def _duplicate_warnings(self, bill: Bill) -> list[str]:
        if not bill.number:
            return []
        rows = self._reader(
            f"SELECT Chave FROM {self._prefix}{self._rule.header.table} WHERE VRef = :v",
            {"v": bill.number})
        return [f"a document with supplier ref {bill.number} already exists"] if rows else []

    # ---- commit -----------------------------------------------------------
    def commit(self, proposal_id: str, operator: str) -> dict:
        plan = self._pending.pop(proposal_id + ":plan")
        if plan is None:
            return {"status": "error", "message": "no staged plan; stage first"}
        try:
            result = self._executor.execute(plan, self._rule)
            self._audit.record(operator=operator, plan=plan, result=result, status="ok")
            self._pending.pop(proposal_id)
            return {"status": "ok", **result}
        except Exception as e:  # noqa: BLE001
            self._audit.record(operator=operator, plan=plan,
                               result={}, status="error")
            return {"status": "error", "message": str(e)[:500]}
