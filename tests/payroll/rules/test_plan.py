from pathlib import Path
from decimal import Decimal
import pytest
from logic.payroll.errors import RuleValidationError
from logic.payroll.rules.plan import (
    PlanStep, CalculationPlan, CalculationPlanBuilder, PHASE_ORDER,
)
from logic.payroll.rules.resolver import RuleResolver, RuleStackSnapshot, ResolvedComponent
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.primitives.base import DEFAULT_REGISTRY
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.public.schemas import RuleCitation


def _make_snapshot_with(components: dict[str, ResolvedComponent]) -> RuleStackSnapshot:
    return RuleStackSnapshot(
        statutory_path=Path("/x/statutory.yaml"),
        cct_path=None,
        company_path=Path("/x/company.yaml"),
        resolved_components=components,
    )


def _comp(code: str, phase: str, primitive: str, params=None, inputs_required=None, type_="earning") -> ResolvedComponent:
    return ResolvedComponent(
        component_code=code, type=type_, phase=phase, primitive=primitive,
        parameters=params or {}, inputs_required=inputs_required or [],
        citations=[RuleCitation(document_path="x", layer="statutory", clause=f"components.{code}")],
    )


def test_phase_order_constant():
    assert PHASE_ORDER == ["input", "gross", "pre_tax_deduction", "tax", "post_tax", "employer_contribution"]


def test_plan_builder_emits_steps_in_phase_order():
    snap = _make_snapshot_with({
        "tsu_employee": _comp("tsu_employee", "tax", "TSUContribution",
                              params={"rate": "0.11", "base_components": ["base_salary"]},
                              inputs_required=["base_salary"], type_="deduction"),
        "base_salary": _comp("base_salary", "gross", "BaseSalary"),
    })
    builder = CalculationPlanBuilder(registry=DEFAULT_REGISTRY)
    plan = builder.build(
        snapshot=snap,
        employee_id="e-1", contract_id="c-1", period_id="2026-05",
        company_id="acme", rounding_policy=RoundingPolicy(),
    )
    phases_emitted = [step.phase for step in plan.steps]
    assert phases_emitted == ["gross", "tax"]
    codes = [s.component_code for s in plan.steps]
    assert codes == ["base_salary", "tsu_employee"]


def test_plan_builder_topological_sort_within_phase():
    snap = _make_snapshot_with({
        "b": _comp("b", "gross", "BaseSalary", inputs_required=["a"]),
        "a": _comp("a", "gross", "BaseSalary"),
    })
    builder = CalculationPlanBuilder(registry=DEFAULT_REGISTRY)
    plan = builder.build(
        snapshot=snap, employee_id="e", contract_id="c",
        period_id="p", company_id="x", rounding_policy=RoundingPolicy(),
    )
    codes = [s.component_code for s in plan.steps]
    assert codes == ["a", "b"]


def test_plan_builder_unknown_primitive_raises():
    snap = _make_snapshot_with({
        "x": _comp("x", "gross", "NonexistentPrimitive"),
    })
    builder = CalculationPlanBuilder(registry=DEFAULT_REGISTRY)
    with pytest.raises(RuleValidationError) as exc:
        builder.build(
            snapshot=snap, employee_id="e", contract_id="c",
            period_id="p", company_id="x", rounding_policy=RoundingPolicy(),
        )
    assert exc.value.code == "UNKNOWN_PRIMITIVE"


def test_plan_builder_missing_dependency_raises():
    snap = _make_snapshot_with({
        "tsu_employee": _comp("tsu_employee", "tax", "TSUContribution",
                              params={"rate": "0.11", "base_components": ["base_salary"]},
                              inputs_required=["base_salary"], type_="deduction"),
    })
    builder = CalculationPlanBuilder(registry=DEFAULT_REGISTRY)
    with pytest.raises(RuleValidationError) as exc:
        builder.build(
            snapshot=snap, employee_id="e", contract_id="c",
            period_id="p", company_id="x", rounding_policy=RoundingPolicy(),
        )
    assert exc.value.code == "UNRESOLVED_DEPENDENCY"


def test_plan_builder_param_schema_validation():
    snap = _make_snapshot_with({
        "tsu_employee": _comp("tsu_employee", "tax", "TSUContribution",
                              params={"rate": "not-a-number"}, type_="deduction"),
    })
    builder = CalculationPlanBuilder(registry=DEFAULT_REGISTRY)
    with pytest.raises(RuleValidationError) as exc:
        builder.build(
            snapshot=snap, employee_id="e", contract_id="c",
            period_id="p", company_id="x", rounding_policy=RoundingPolicy(),
        )
    assert exc.value.code == "PARAMETER_SCHEMA_INVALID"
