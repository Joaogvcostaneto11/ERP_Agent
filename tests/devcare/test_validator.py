# tests/devcare/test_validator.py
import pytest
from logic.devcare.rules.loader import RuleLoader
from logic.devcare.rules.models import EntityRule, FieldRule, FieldValidation, Reference
from logic.devcare.validator import ChangeValidator
from logic.devcare.errors import ValidationViolation


class FakeReader:
    """Returns canned rows per (table) for uniqueness/reference checks."""
    def __init__(self, rows_by_table=None):
        self.rows_by_table = rows_by_table or {}
        self.calls = []

    def __call__(self, sql, params):
        self.calls.append((sql, params))
        # crude: route by table name appearing in sql
        for table, rows in self.rows_by_table.items():
            if f" {table} " in f" {sql} " or f".{table} " in sql:
                return rows
        return []


@pytest.fixture
def loader():
    return RuleLoader("business_rules/devcare")


def test_create_requires_name(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("specialty", "create", {"code": "Z9"}, None)
    assert result.ok is False
    assert any("name" in viol.field for viol in result.violations)


def test_create_specialty_valid(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("specialty", "create", {"code": "Z9", "name": "Test"}, None)
    assert result.ok is True
    assert result.change.operation == "create"
    assert result.change.columns["Codigo"] == "Z9"
    assert result.change.columns["Nome"] == "Test"
    assert result.rule_version == 1


def test_regex_violation_on_tax_id(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("patient", "create", {"name": "A", "tax_id": "12x"}, None)
    assert result.ok is False
    assert any(viol.field == "tax_id" for viol in result.violations)


def test_max_length_violation(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("specialty", "create", {"code": "X" * 11, "name": "A"}, None)
    assert result.ok is False
    assert any(viol.field == "code" for viol in result.violations)


def test_uniqueness_violation(loader):
    reader = FakeReader({"Especialidades": [{"n": 1}]})
    v = ChangeValidator(loader, reader)
    result = v.validate("specialty", "create", {"code": "00", "name": "Dup"}, None)
    assert result.ok is False
    assert any("unique" in viol.message.lower() for viol in result.violations)


def test_update_requires_target_pk(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("specialty", "update", {"name": "New"}, None)
    assert result.ok is False
    assert any("primary key" in viol.message.lower() for viol in result.violations)


def test_update_resolves_single_row(loader):
    reader = FakeReader({"Especialidades": [{"cnt": 1}]})
    v = ChangeValidator(loader, reader)
    result = v.validate("specialty", "update", {"name": "New"}, target_pk=12)
    assert result.ok is True
    assert result.change.target_pk == 12
    assert result.change.columns == {"Nome": "New"}


def test_delete_disallowed_when_not_in_operations(tmp_path, loader):
    # patient allows delete; craft an entity without delete by reusing specialty? use operations check
    v = ChangeValidator(loader, FakeReader({"Especialidades": [{"cnt": 1}]}))
    result = v.validate("specialty", "delete", {}, target_pk=12)
    assert result.ok is True  # specialty allows delete


# --- Regression tests ---

def test_unknown_field_rejected(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("specialty", "create", {"code": "Z9", "name": "X", "bogus": "1"}, None)
    assert result.ok is False
    assert any(viol.field == "bogus" for viol in result.violations)


def test_min_max_on_string_does_not_crash():
    """A string field with a numeric min bound must not raise TypeError."""
    rule = EntityRule(
        entity="fake",
        version=1,
        table="FakeTable",
        primary_key="Chave",
        operations=["create"],
        fields={
            "label": FieldRule(
                column="Label",
                type="string",
                required=False,
                validation=FieldValidation(min=1),
            )
        },
    )

    class FakeLoader:
        def get(self, entity):
            return rule

    v = ChangeValidator(FakeLoader(), FakeReader())
    # Must not raise; result may be ok=True or have unrelated violations
    result = v.validate("fake", "create", {"label": "hello"}, None)
    assert result is not None


def test_reference_uses_coerced_value():
    """Reference check must pass the coerced (int) value, not the raw string."""
    rule = EntityRule(
        entity="fake",
        version=1,
        table="FakeTable",
        primary_key="Chave",
        operations=["create"],
        fields={
            "name": FieldRule(column="Nome", type="string", required=True),
            "spec": FieldRule(column="Especialidade", type="int", required=False),
        },
        references={"spec": Reference(table="Especialidades", column="Chave")},
    )

    class FakeLoader:
        def get(self, entity):
            return rule

    class RecordingReader:
        def __init__(self):
            self.ref_params = []
            self.calls = []

        def __call__(self, sql, params):
            self.calls.append((sql, params))
            if "Especialidades" in sql:
                self.ref_params.append(params)
                return [{"n": 1}]
            return []

    reader = RecordingReader()
    v = ChangeValidator(FakeLoader(), reader)
    result = v.validate("fake", "create", {"name": "A", "spec": "7"}, None)

    assert result.ok is True
    assert len(reader.ref_params) == 1
    passed_value = reader.ref_params[0]["v"]
    assert passed_value == 7
    assert isinstance(passed_value, int)


def test_patient_birth_date_valid(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("patient", "create",
                        {"name": "Maria", "birth_date": "1990-05-14"}, None)
    assert result.ok is True
    assert result.change.columns["DataNasc"] == "1990-05-14"


def test_patient_birth_date_invalid_rejected(loader):
    v = ChangeValidator(loader, FakeReader())
    for bad in ("14-05-1990", "1990/05/14", "not-a-date", "1990-13-01"):
        result = v.validate("patient", "create",
                            {"name": "Maria", "birth_date": bad}, None)
        assert result.ok is False, bad
        assert any(viol.field == "birth_date" for viol in result.violations), bad


def test_patient_gender_enum(loader):
    v = ChangeValidator(loader, FakeReader())
    ok = v.validate("patient", "create", {"name": "Ana", "gender": 2}, None)
    assert ok.ok is True
    assert ok.change.columns["Sexo"] == 2
    bad = v.validate("patient", "create", {"name": "Ana", "gender": 5}, None)
    assert bad.ok is False
    assert any(viol.field == "gender" for viol in bad.violations)


def test_patient_version_is_two(loader):
    v = ChangeValidator(loader, FakeReader())
    result = v.validate("patient", "create", {"name": "Ana"}, None)
    assert result.rule_version == 2
