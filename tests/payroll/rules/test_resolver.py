from pathlib import Path
from logic.payroll.rules.resolver import RuleStackSnapshot, ResolvedComponent
from logic.payroll.public.schemas import RuleCitation


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
