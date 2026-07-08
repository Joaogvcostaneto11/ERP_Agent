from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.rules.models import (
    ComponentDecl, RuleDocument, RuleDocumentMetadata,
)


def test_component_decl_minimal():
    c = ComponentDecl(
        type="earning",
        phase="gross",
        primitive="BaseSalary",
        parameters={},
        inputs_required=[],
        taxable=True,
    )
    assert c.disabled is False
    assert c.locked is False


def test_component_decl_unknown_phase_rejected():
    with pytest.raises(ValidationError):
        ComponentDecl(type="earning", phase="bogus", primitive="X", parameters={}, inputs_required=[])


def test_component_decl_unknown_type_rejected():
    with pytest.raises(ValidationError):
        ComponentDecl(type="freebie", phase="gross", primitive="X", parameters={}, inputs_required=[])


def test_rule_document_with_components():
    doc = RuleDocument(
        metadata=RuleDocumentMetadata(jurisdiction="PT", effective_from="2026-01-01", version="2026.1"),
        components={
            "base_salary": ComponentDecl(
                type="earning", phase="gross", primitive="BaseSalary",
                parameters={}, inputs_required=[], taxable=True,
            ),
            "tsu_employee": ComponentDecl(
                type="deduction", phase="tax", primitive="TSUContribution",
                parameters={"rate": "0.11", "base_components": ["base_salary"]},
                inputs_required=["base_salary"],
            ),
        },
    )
    assert "base_salary" in doc.components
    assert doc.components["tsu_employee"].primitive == "TSUContribution"


def test_disabled_component_via_explicit_flag():
    c = ComponentDecl(
        type="earning", phase="gross", primitive="X",
        parameters={}, inputs_required=[], disabled=True,
    )
    assert c.disabled is True
