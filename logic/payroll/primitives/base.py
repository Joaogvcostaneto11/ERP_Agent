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


class Primitive(Protocol):
    name: str
    parameter_schema: type[BaseModel]
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]

    def execute(self, params: BaseModel, inputs: BaseModel, context: ExecutionContext) -> PrimitiveResult: ...


class PrimitiveRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, type[Primitive]] = {}

    def register(self, name: str, primitive_cls: type[Primitive]) -> None:
        if name in self._by_name:
            raise ValueError(f"Primitive {name!r} already registered")
        self._by_name[name] = primitive_cls

    def get(self, name: str) -> type[Primitive]:
        return self._by_name[name]


DEFAULT_REGISTRY = PrimitiveRegistry()


def register(name: str, registry: PrimitiveRegistry | None = None):
    target = registry if registry is not None else DEFAULT_REGISTRY

    def decorator(cls):
        target.register(name, cls)
        return cls

    return decorator
