import pytest
from pydantic import ValidationError
from logic.devcare.rules.models import EntityRule, FieldRule


def test_minimal_entity_rule():
    rule = EntityRule(
        entity="specialty", version=1, table="Especialidades",
        primary_key="Chave", operations=["create", "update", "delete"],
        soft_delete={"column": "Hist", "active_value": 0, "deleted_value": 1},
        fields={"name": {"column": "Nome", "type": "string", "required": True}},
    )
    assert rule.fields["name"].column == "Nome"
    assert rule.fields["name"].required is True
    assert "create" in rule.operations


def test_unknown_field_type_rejected():
    with pytest.raises(ValidationError):
        FieldRule(column="X", type="datetime-ish")


def test_reference_and_uniqueness_optional():
    rule = EntityRule(
        entity="x", version=1, table="T", primary_key="Chave",
        operations=["create"], fields={"a": {"column": "A", "type": "int"}},
    )
    assert rule.references == {}
    assert rule.uniqueness == []
    assert rule.soft_delete is None
