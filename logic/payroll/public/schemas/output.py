from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class RuleCitation(BaseModel):
    model_config = ConfigDict(strict=True)

    document_path: str
    layer: Literal["statutory", "cct", "company", "contract"]
    component_code: Optional[str] = None
    clause: str


class AuditTrailEntry(BaseModel):
    model_config = ConfigDict(strict=True)

    step_index: int = Field(ge=0)
    primitive: str
    inputs_snapshot: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    rule_citation: RuleCitation
    timestamp: datetime


class PayslipLine(BaseModel):
    model_config = ConfigDict(strict=True)

    component_code: str
    description: str
    amount: Decimal
    quantity: Optional[Decimal] = None
    rate: Optional[Decimal] = None
    tax_treatment: Literal["taxable", "exempt", "partially_exempt"]
    exempt_amount: Decimal = Decimal("0")
    source_audit_ref: int = Field(ge=0)


class PayslipResult(BaseModel):
    model_config = ConfigDict(strict=True)

    period_id: str
    employee_id: str
    gross_earnings: list[PayslipLine] = Field(default_factory=list)
    deductions: list[PayslipLine] = Field(default_factory=list)
    employer_contributions: list[PayslipLine] = Field(default_factory=list)
    net_pay: Decimal
    audit: list[AuditTrailEntry] = Field(default_factory=list)
