from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from logic.payroll.errors import RuleValidationError
from logic.payroll.primitives.base import PrimitiveRegistry
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.public.schemas import RuleCitation
from logic.payroll.rules.resolver import RuleStackSnapshot, ResolvedComponent


PHASE_ORDER = [
    "input",
    "gross",
    "pre_tax_deduction",
    "tax",
    "post_tax",
    "employer_contribution",
]


class PlanStep(BaseModel):
    model_config = ConfigDict(strict=True)

    index: int = Field(ge=0)
    phase: str
    component_code: str
    primitive_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    inputs_required: list[str] = Field(default_factory=list)
    citations: list[RuleCitation] = Field(default_factory=list)


class CalculationPlan(BaseModel):
    model_config = ConfigDict(strict=True)

    employee_id: str
    contract_id: str
    period_id: str
    company_id: str
    rounding_policy: RoundingPolicy
    steps: list[PlanStep] = Field(default_factory=list)


def _topological_sort(components: list[ResolvedComponent]) -> list[ResolvedComponent]:
    by_code = {c.component_code: c for c in components}
    visited: set[str] = set()
    ordered: list[ResolvedComponent] = []

    def visit(c: ResolvedComponent, stack: tuple[str, ...] = ()) -> None:
        if c.component_code in visited:
            return
        if c.component_code in stack:
            raise RuleValidationError(
                code="CYCLIC_DEPENDENCY",
                msg_pt=f"ciclo de dependencias detectado: {stack + (c.component_code,)}",
                msg_en=f"cyclic dependency detected: {stack + (c.component_code,)}",
            )
        for dep in c.inputs_required:
            if dep in by_code:
                visit(by_code[dep], stack + (c.component_code,))
        visited.add(c.component_code)
        ordered.append(c)

    for c in components:
        visit(c)
    return ordered


class CalculationPlanBuilder:
    def __init__(self, registry: PrimitiveRegistry) -> None:
        self._registry = registry

    def build(
        self,
        snapshot: RuleStackSnapshot,
        employee_id: str,
        contract_id: str,
        period_id: str,
        company_id: str,
        rounding_policy: RoundingPolicy,
    ) -> CalculationPlan:
        all_codes = set(snapshot.resolved_components.keys())
        for comp in snapshot.resolved_components.values():
            for dep in comp.inputs_required:
                if dep not in all_codes:
                    raise RuleValidationError(
                        code="UNRESOLVED_DEPENDENCY",
                        msg_pt=f"componente {comp.component_code!r} depende de {dep!r}, que nao existe",
                        msg_en=f"component {comp.component_code!r} depends on {dep!r}, which does not exist in the resolved stack",
                    )
            try:
                self._registry.get(comp.primitive)
            except KeyError as ex:
                raise RuleValidationError(
                    code="UNKNOWN_PRIMITIVE",
                    msg_pt=f"primitiva {comp.primitive!r} nao registada",
                    msg_en=f"primitive {comp.primitive!r} is not registered",
                ) from ex
            prim_cls = self._registry.get(comp.primitive)
            try:
                # strict=False allows YAML-derived stringified Decimals to coerce
                # into Decimal at this boundary; in-Python construction of the
                # parameter schema remains strict per its ConfigDict.
                prim_cls.parameter_schema.model_validate(comp.parameters, strict=False)
            except ValidationError as ex:
                raise RuleValidationError(
                    code="PARAMETER_SCHEMA_INVALID",
                    msg_pt=f"parametros invalidos para {comp.component_code!r}: {ex}",
                    msg_en=f"invalid parameters for {comp.component_code!r}: {ex}",
                ) from ex

        steps: list[PlanStep] = []
        for phase in PHASE_ORDER:
            in_phase = [c for c in snapshot.resolved_components.values() if c.phase == phase]
            if not in_phase:
                continue
            for comp in _topological_sort(in_phase):
                steps.append(PlanStep(
                    index=len(steps),
                    phase=phase,
                    component_code=comp.component_code,
                    primitive_name=comp.primitive,
                    parameters=comp.parameters,
                    inputs_required=comp.inputs_required,
                    citations=comp.citations,
                ))

        return CalculationPlan(
            employee_id=employee_id,
            contract_id=contract_id,
            period_id=period_id,
            company_id=company_id,
            rounding_policy=rounding_policy,
            steps=steps,
        )
