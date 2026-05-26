from pathlib import Path
from logic.payroll.rules.resolver import RuleStackSnapshot, ResolvedComponent
from logic.payroll.public.schemas import RuleCitation
from logic.payroll.rules.resolver import RuleResolver
from logic.payroll.rules.loader import RuleLoader


def test_rule_stack_snapshot_is_frozen():
    import dataclasses
    snap = RuleStackSnapshot(
        statutory_path=Path("/x/statutory.yaml"),
        cct_path=None,
        company_path=Path("/x/company.yaml"),
        resolved_components={},
    )
    assert dataclasses.is_dataclass(snap)
    import pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.cct_path = Path("/y/cct.yaml")  # type: ignore


def test_resolved_component_holds_citations():
    c = RuleCitation(document_path="x", layer="statutory", clause="components.base_salary")
    rc = ResolvedComponent(
        component_code="base_salary",
        type="earning",
        phase="gross",
        primitive="BaseSalary",
        parameters={},
        inputs_required=[],
        taxable=True,
        subject_to_tsu=True,
        locked=False,
        citations=[c],
    )
    assert rc.citations[0].layer == "statutory"


def _write(tmp_path, name, body):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_resolver_picks_up_statutory_only(tmp_path):
    statutory = _write(tmp_path, "statutory.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
""")
    company = _write(tmp_path, "company.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
""")
    loader = RuleLoader()
    resolver = RuleResolver(loader)
    snapshot = resolver.resolve(statutory_path=statutory, company_path=company)
    assert "base_salary" in snapshot.resolved_components
    cits = snapshot.resolved_components["base_salary"].citations
    assert len(cits) == 1
    assert cits[0].layer == "statutory"


def test_resolver_company_layer_overrides_statutory_scalar(tmp_path):
    statutory = _write(tmp_path, "statutory.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
""")
    company = _write(tmp_path, "company.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.105"
    inputs_required: ["base_salary"]
""")
    loader = RuleLoader()
    resolver = RuleResolver(loader)
    snapshot = resolver.resolve(statutory_path=statutory, company_path=company)
    tsu = snapshot.resolved_components["tsu_employee"]
    assert tsu.parameters["rate"] == "0.105"
    layers = [c.layer for c in tsu.citations]
    assert "statutory" in layers and "company" in layers


def test_resolver_company_adds_new_component(tmp_path):
    statutory = _write(tmp_path, "statutory.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
""")
    company = _write(tmp_path, "company.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  meal_allowance:
    type: earning
    phase: gross
    primitive: MealAllowance
    parameters:
      daily_rate: "6.00"
    inputs_required: []
""")
    loader = RuleLoader()
    resolver = RuleResolver(loader)
    snapshot = resolver.resolve(statutory_path=statutory, company_path=company)
    assert "meal_allowance" in snapshot.resolved_components
    assert snapshot.resolved_components["meal_allowance"].citations[0].layer == "company"


def test_resolver_disabled_drops_component(tmp_path):
    statutory = _write(tmp_path, "statutory.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
""")
    company = _write(tmp_path, "company.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
    disabled: true
""")
    loader = RuleLoader()
    resolver = RuleResolver(loader)
    snapshot = resolver.resolve(statutory_path=statutory, company_path=company)
    assert "base_salary" not in snapshot.resolved_components


def test_resolver_locked_field_blocks_higher_override(tmp_path):
    from logic.payroll.errors import RuleValidationError
    import pytest
    statutory = _write(tmp_path, "statutory.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
    inputs_required: ["base_salary"]
    locked: true
""")
    company = _write(tmp_path, "company.yaml", """
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.105"
    inputs_required: ["base_salary"]
""")
    loader = RuleLoader()
    resolver = RuleResolver(loader)
    with pytest.raises(RuleValidationError) as exc:
        resolver.resolve(statutory_path=statutory, company_path=company)
    assert exc.value.code == "LOCKED_COMPONENT_OVERRIDE"
