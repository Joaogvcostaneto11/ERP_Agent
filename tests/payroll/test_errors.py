import pytest
from logic.payroll.errors import (
    PayrollError, RuleLoadError, RuleValidationError, MissingInput,
    RuleViolation, ImmutablePeriod, PeriodInProgress, EngineInvariantError,
)


def test_payroll_error_holds_code_and_messages():
    err = PayrollError(code="X1", msg_pt="erro", msg_en="error")
    assert err.code == "X1"
    assert err.msg_pt == "erro"
    assert err.msg_en == "error"
    assert err.citation is None
    assert str(err) == "error"


def test_payroll_error_optional_citation_is_a_dict():
    citation = {
        "document_path": "business_rules/payroll/statutory_pt.yaml",
        "layer": "statutory",
        "clause": "components.tsu_employee.rate",
    }
    err = PayrollError("X1", "erro", "error", citation=citation)
    assert err.citation == citation


@pytest.mark.parametrize(
    "cls",
    [RuleLoadError, RuleValidationError, MissingInput, RuleViolation,
     ImmutablePeriod, PeriodInProgress, EngineInvariantError],
)
def test_subclasses_inherit_payroll_error(cls):
    err = cls(code="X1", msg_pt="pt", msg_en="en")
    assert isinstance(err, PayrollError)
    assert err.code == "X1"


def test_can_be_raised_and_caught():
    with pytest.raises(RuleViolation) as exc_info:
        raise RuleViolation(code="LOCKED_FIELD", msg_pt="campo bloqueado", msg_en="locked field")
    assert exc_info.value.code == "LOCKED_FIELD"
