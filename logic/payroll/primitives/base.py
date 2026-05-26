from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field
from logic.payroll.public.schemas import (
    Employee, Contract, Company, PayrollPeriod, RuleCitation,
)
from logic.payroll.primitives.rounding import RoundingPolicy
from logic.payroll.clock import Clock


class PrimitiveResult(BaseModel):
    model_config = ConfigDict(strict=True)

    amount: Decimal
    quantity: Decimal | None = None
    rate: Decimal | None = None
    tax_treatment: Literal["taxable", "exempt", "partially_exempt"] = "taxable"
    exempt_amount: Decimal = Decimal("0")
    breakdown: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""
    citations: list[RuleCitation] = Field(default_factory=list)


@dataclass(frozen=True)
class ExecutionContext:
    period: PayrollPeriod
    contract: Contract
    employee: Employee
    company: Company
    rounding_policy: RoundingPolicy
    clock: Clock
