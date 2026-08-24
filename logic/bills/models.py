from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, field_validator


class PageText(BaseModel):
    page: int
    text: str


class BillLine(BaseModel):
    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    vat_rate: Decimal | None = None
    total: Decimal | None = None

    @field_validator("vat_rate", mode="before")
    @classmethod
    def _strip_percent(cls, v):
        # OCR/LLM output carries the rate as "23%"; drop the sign and keep 23.
        if isinstance(v, str):
            return v.replace("%", "").strip()
        return v


class Bill(BaseModel):
    supplier_name: str
    supplier_tax_id: str | None = None
    # Extraction-only: kept so the model has somewhere to put the OTHER tax
    # number on the page and stops mistaking it for the issuer's. Deliberately
    # not mapped in the rule document and not shown in the UI.
    buyer_tax_id: str | None = None
    number: str | None = None
    issue_date: date | None = None
    due_date: date | None = None
    currency: str | None = None
    net_total: Decimal | None = None
    vat_total: Decimal | None = None
    gross_total: Decimal | None = None
    lines: list[BillLine] = []
    confidence: dict[str, float] = {}

    @field_validator("supplier_name", mode="before")
    @classmethod
    def _reject_blank_name(cls, v):
        # An illegible letterhead comes back as null or as "" / "   ". Both mean
        # the same thing, so both must fail the required-field contract: a blank
        # name would otherwise reach Matcher as a LIKE '%%' pattern that returns
        # every supplier in the database as an "ambiguous" candidate.
        if isinstance(v, str):
            v = v.strip()
            if not v:
                raise ValueError("supplier_name is blank")
        return v


class Candidate(BaseModel):
    chave: int
    label: str
    score: float


class MatchResult(BaseModel):
    status: Literal["matched", "ambiguous", "new"]
    chave: int | None = None
    # Name of the matched record, so the UI can show WHICH supplier/article a
    # bare "matched" badge picked. Display only; nothing is written from it.
    label: str | None = None
    candidates: list[Candidate] = []
    proposed_new: dict | None = None
    confirmed: bool = False


class BillProposal(BaseModel):
    proposal_id: str
    bill: Bill
    supplier_match: MatchResult
    line_matches: list[MatchResult] = []
    warnings: list[str] = []


class LinePlan(BaseModel):
    article: MatchResult
    columns: dict


class WritePlan(BaseModel):
    proposal_id: str
    supplier: MatchResult
    header: dict
    lines: list[LinePlan]
    rule_doc: str
    rule_version: int


_TOL = Decimal("0.02")


def arithmetic_warnings(bill: Bill) -> list[str]:
    """Flag internal inconsistencies without failing; the operator resolves them."""
    warnings: list[str] = []
    if bill.net_total is not None and bill.vat_total is not None \
            and bill.gross_total is not None:
        if abs((bill.net_total + bill.vat_total) - bill.gross_total) > _TOL:
            warnings.append(
                f"gross_total {bill.gross_total} != net {bill.net_total} + vat {bill.vat_total}")
    line_totals = [ln.total for ln in bill.lines if ln.total is not None]
    if line_totals and bill.net_total is not None:
        summed = sum(line_totals, Decimal("0"))
        if abs(summed - bill.net_total) > _TOL:
            warnings.append(
                f"sum of line totals {summed} != net_total {bill.net_total}")
    return warnings
