from __future__ import annotations
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field
from logic.payroll.primitives.base import (
    PrimitiveResult, ExecutionContext, register,
)
from logic.payroll.errors import MissingInput


class TSUContributionParams(BaseModel):
    model_config = ConfigDict(strict=True)

    rate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    base_components: list[str] = Field(min_length=1)


class TSUContributionInputs(BaseModel):
    model_config = ConfigDict(strict=True)

    component_values: dict[str, Decimal] = Field(default_factory=dict)


@register("TSUContribution")
class TSUContribution:
    name = "TSUContribution"
    parameter_schema = TSUContributionParams
    input_schema = TSUContributionInputs
    output_schema = PrimitiveResult

    def execute(
        self,
        params: TSUContributionParams,
        inputs: TSUContributionInputs,
        context: ExecutionContext,
    ) -> PrimitiveResult:
        base = Decimal("0")
        for code in params.base_components:
            if code not in inputs.component_values:
                raise MissingInput(
                    code="TSU_MISSING_BASE_COMPONENT",
                    msg_pt=f"componente base {code!r} em falta para TSU",
                    msg_en=f"missing base component {code!r} for TSU contribution",
                )
            base += inputs.component_values[code]
        gross = base * params.rate
        amount = context.rounding_policy.apply(gross)
        return PrimitiveResult(
            amount=amount,
            rate=params.rate,
            tax_treatment="taxable",
            notes=f"TSU = {params.rate} * sum({', '.join(params.base_components)})",
        )
