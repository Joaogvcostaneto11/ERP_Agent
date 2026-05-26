from __future__ import annotations
from pydantic import BaseModel, ConfigDict
from logic.payroll.primitives.base import (
    PrimitiveResult, ExecutionContext, register,
)


class BaseSalaryParams(BaseModel):
    model_config = ConfigDict(strict=True)


class BaseSalaryInputs(BaseModel):
    model_config = ConfigDict(strict=True)


@register("BaseSalary")
class BaseSalary:
    name = "BaseSalary"
    parameter_schema = BaseSalaryParams
    input_schema = BaseSalaryInputs
    output_schema = PrimitiveResult

    def execute(
        self,
        params: BaseSalaryParams,
        inputs: BaseSalaryInputs,
        context: ExecutionContext,
    ) -> PrimitiveResult:
        amount = context.rounding_policy.apply(context.contract.base_monthly_salary)
        return PrimitiveResult(
            amount=amount,
            tax_treatment="taxable",
            notes=f"Base monthly salary per contract {context.contract.contract_id}",
        )
