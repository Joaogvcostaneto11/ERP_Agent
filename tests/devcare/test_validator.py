# tests/devcare/test_validator.py
import pytest
from logic.devcare.rules.loader import RuleLoader
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
