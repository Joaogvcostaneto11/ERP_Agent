from __future__ import annotations
import uuid
from typing import Any, Callable

from pydantic import ValidationError

from logic.bills.extract.image import prepare
from logic.bills.extract.media import sniff
from logic.bills.extract.parser import BillParser
from logic.bills.matching import Matcher, line_proposal, supplier_proposal
from logic.bills.models import (Bill, BillLine, BillProposal, LinePlan,
                                MatchResult, WritePlan, arithmetic_warnings)
from logic.bills.pending import PendingProposalStore
from logic.bills.rules.models import PurchaseInvoiceRule
from logic.bills.tax_id import pt_nif_is_valid


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
    def upload(self, data: bytes) -> BillProposal:
        bill = self._extract(data)
        warnings: list[str] = []
        if pt_nif_is_valid(bill.supplier_tax_id) is False:
            # A plausible-but-wrong NIF can match the wrong existing supplier
            # or seed a new one with a bad fiscal number, so it must be
            # blanked BEFORE matching, which keys on this field.
            warnings.append(
                f"supplier tax id {bill.supplier_tax_id!r} failed the NIF "
                "check digit and was cleared; please re-enter it")
            bill.supplier_tax_id = None
        supplier_match = self._matcher.match_supplier(bill)
        line_matches = [self._matcher.match_line(ln) for ln in bill.lines]
        proposal = BillProposal(
            proposal_id="bill_" + uuid.uuid4().hex[:12], bill=bill,
            supplier_match=supplier_match, line_matches=line_matches,
            warnings=warnings + arithmetic_warnings(bill))
        self._pending.put(proposal.proposal_id, proposal)
        return proposal

    def _extract(self, data: bytes) -> Bill:
        """PDFs go through Tesseract; images go straight to Claude vision, which
        reads skewed phone photos and preserves table layout that flat OCR text
        would destroy."""
        media_type = sniff(data)
        if media_type == "application/pdf":
            return self._parser.parse(self._ocr(data))
        return self._parser.parse_image(*prepare(data, media_type))

    # ---- stage ------------------------------------------------------------
    def _bill_value(self, bill: Bill, source: str):
        # getattr default keeps mapped-but-unextracted fields (e.g. notes) safe.
        return getattr(bill, source.split(".", 1)[1], None)

    def _line_value(self, line: BillLine, source: str):
        return getattr(line, source.split(".", 1)[1], None)

    def _build_header(self, bill: Bill) -> tuple[dict, list[dict]]:
        cols, violations = {}, []
        for name, fr in self._rule.header.fields.items():
            if fr.source.endswith(".match"):
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

    @staticmethod
    def _refresh_proposed_new(proposal: BillProposal) -> None:
        """Rebuild every 'new' record's columns from the EDITED bill.

        proposed_new is built by the Matcher at upload time, from the values the
        model extracted. The operator then corrects those values in the UI — a
        misread NIF, say — but only bill.* is editable, so a stale proposed_new
        would insert the ORIGINAL wrong value into Entidades. A created supplier
        is permanent master data and NCont feeds AT/SAF-T reporting, so the
        edited bill has to win. Re-deriving (rather than patching keys in place)
        also keeps the column set exactly the one matching.*.create_columns
        whitelists."""
        if proposal.supplier_match.status == "new":
            proposal.supplier_match.proposed_new = supplier_proposal(proposal.bill)
        for line, lm in zip(proposal.bill.lines, proposal.line_matches):
            if lm.status == "new":
                lm.proposed_new = line_proposal(line)

    def stage(self, proposal_id: str, edited: dict) -> dict:
        # Any previously-staged plan is now stale — clear it so only a stage()
        # call that ends ok:True can leave a committable plan for commit().
        self._pending.pop(proposal_id + ":plan")
        try:
            proposal = BillProposal.model_validate(edited)
        except ValidationError as e:
            # The operator can clear a required field on the review screen (the
            # UI posts an emptied input as null). Report it in the violations
            # shape the screen already renders, rather than letting pydantic's
            # ValidationError — not a RuntimeError — escape app.py as a 500.
            return {"ok": False, "violations": [
                {"field": ".".join(str(p) for p in err["loc"]),
                 "message": err["msg"]} for err in e.errors()]}
        self._refresh_proposed_new(proposal)
        self._pending.put(proposal_id, proposal)  # keep latest edits
        violations: list[dict] = []

        # The upload-time guard blanks a bad NIF before the operator has seen
        # it; here they typed it themselves, so it must be reported rather
        # than silently discarded. is False (not a truthiness check) so a
        # foreign tax ID, which pt_nif_is_valid reports as None, passes
        # through untouched.
        if pt_nif_is_valid(proposal.bill.supplier_tax_id) is False:
            violations.append({
                "field": "supplier_tax_id",
                "message": f"supplier tax id {proposal.bill.supplier_tax_id!r} "
                           "failed the NIF check digit"})

        if len(proposal.bill.lines) != len(proposal.line_matches):
            violations.append({"field": "lines",
                               "message": "line count does not match line_matches count"})

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
