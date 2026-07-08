from __future__ import annotations
from decimal import Decimal
from logic.payroll.primitives.base import ExecutionContext, PrimitiveRegistry, PrimitiveResult
from logic.payroll.rules.plan import CalculationPlan, PlanStep
from logic.payroll.public.schemas import (
    AuditTrailEntry, PayslipLine, PayslipResult, TimeInput,
)
from logic.payroll.engine.audit import select_primary_citation


class Executor:
    def __init__(self, registry: PrimitiveRegistry) -> None:
        self._registry = registry

    def execute(
        self,
        plan: CalculationPlan,
        context: ExecutionContext,
        time_input: TimeInput,
    ) -> PayslipResult:
        gross_earnings: list[PayslipLine] = []
        deductions: list[PayslipLine] = []
        employer_contributions: list[PayslipLine] = []
        audit: list[AuditTrailEntry] = []
        produced: dict[str, Decimal] = {}

        for step in plan.steps:
            prim_cls = self._registry.get(step.primitive_name)
            # strict=False to coerce YAML-derived stringified Decimals at the boundary.
            params = prim_cls.parameter_schema.model_validate(step.parameters, strict=False)
            inputs_payload = self._build_inputs(step, prim_cls, produced)
            inputs = prim_cls.input_schema.model_validate(inputs_payload)
            primitive = prim_cls()
            result: PrimitiveResult = primitive.execute(params, inputs, context)

            audit_entry = AuditTrailEntry(
                step_index=step.index,
                primitive=step.primitive_name,
                inputs_snapshot=inputs.model_dump(mode="json"),
                output=result.model_dump(mode="json"),
                rule_citation=select_primary_citation(step.citations),
                timestamp=context.clock.now(),
            )
            audit.append(audit_entry)

            line = PayslipLine(
                component_code=step.component_code,
                description=result.notes or step.component_code,
                amount=result.amount,
                quantity=result.quantity,
                rate=result.rate,
                tax_treatment=result.tax_treatment,
                exempt_amount=result.exempt_amount,
                source_audit_ref=step.index,
            )
            self._route_line(step, line, gross_earnings, deductions, employer_contributions)
            produced[step.component_code] = result.amount

        gross_total = sum((l.amount for l in gross_earnings), start=Decimal("0"))
        deduction_total = sum((l.amount for l in deductions), start=Decimal("0"))
        net = context.rounding_policy.apply(gross_total - deduction_total)

        return PayslipResult(
            period_id=plan.period_id,
            employee_id=plan.employee_id,
            gross_earnings=gross_earnings,
            deductions=deductions,
            employer_contributions=employer_contributions,
            net_pay=net,
            audit=audit,
        )

    @staticmethod
    def _build_inputs(step: PlanStep, prim_cls, produced: dict[str, Decimal]) -> dict:
        """Construct the inputs payload for a primitive based on its declared input schema."""
        # Convention: if a primitive's input_schema has a `component_values: dict[str, Decimal]` field,
        # we populate it with the upstream component amounts named in `step.inputs_required`.
        field_names = set(prim_cls.input_schema.model_fields.keys())
        payload: dict = {}
        if "component_values" in field_names:
            payload["component_values"] = {
                code: produced[code] for code in step.inputs_required if code in produced
            }
        return payload

    @staticmethod
    def _route_line(step: PlanStep, line: PayslipLine,
                    gross: list[PayslipLine], dedu: list[PayslipLine], emp: list[PayslipLine]) -> None:
        if step.phase in ("gross",):
            gross.append(line)
        elif step.phase in ("pre_tax_deduction", "tax", "post_tax"):
            dedu.append(line)
        elif step.phase == "employer_contribution":
            emp.append(line)
        # phase "input" produces no payslip line
