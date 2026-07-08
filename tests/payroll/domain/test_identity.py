from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.public.schemas.identity import (
    FiscalProfile, CCTReference, Company,
)
from logic.payroll.rounding import RoundingPolicy


def test_fiscal_profile_defaults():
    fp = FiscalProfile(irs_table_code="solteiro_sem_dependentes")
    assert fp.dependents == 0
    assert fp.has_disability is False
    assert fp.residency_status == "resident"


def test_fiscal_profile_negative_dependents_rejected():
    with pytest.raises(ValidationError):
        FiscalProfile(irs_table_code="solteiro_sem_dependentes", dependents=-1)


def test_fiscal_profile_residency_enum():
    fp = FiscalProfile(irs_table_code="x", residency_status="non_habitual_resident")
    assert fp.residency_status == "non_habitual_resident"
    with pytest.raises(ValidationError):
        FiscalProfile(irs_table_code="x", residency_status="weird")


def test_cct_reference_valid():
    c = CCTReference(cct_id="cct-metalurgia-2025", cct_version="2025.1", role_category_code="op3")
    assert c.cct_id == "cct-metalurgia-2025"


def test_cct_reference_missing_field_rejected():
    with pytest.raises(ValidationError):
        CCTReference(cct_id="x", cct_version="1")  # missing role_category_code


def test_company_with_rounding_policy():
    c = Company(
        company_id="acme",
        legal_name="Acme, Lda.",
        tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )
    assert c.default_subsidio_payment_mode == "duodecimos"


def test_company_subsidio_mode_enum():
    c = Company(
        company_id="acme", legal_name="Acme", tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
        default_subsidio_payment_mode="one_shot",
    )
    assert c.default_subsidio_payment_mode == "one_shot"
    with pytest.raises(ValidationError):
        Company(
            company_id="x", legal_name="x", tax_id="x",
            default_rounding_policy=RoundingPolicy(),
            default_subsidio_payment_mode="quincenal",
        )


from datetime import date as _date
from logic.payroll.public.schemas.identity import (
    Contract, Employee, CompensationEntitlement, CompensationPackage,
)


def _valid_contract_kwargs(**overrides):
    base = dict(
        contract_id="c-1",
        employee_id="e-1",
        type="CT",
        start_date=_date(2025, 1, 1),
        end_date=None,
        role_category="developer",
        weekly_hours=Decimal("40"),
        fte_percent=Decimal("1.0"),
        base_monthly_salary=Decimal("1500"),
        cct_reference=None,
        company_id="acme",
        pay_frequency="monthly",
    )
    base.update(overrides)
    return base


def test_contract_valid():
    c = Contract(**_valid_contract_kwargs())
    assert c.type == "CT"
    assert c.pay_frequency == "monthly"


def test_contract_unknown_type_rejected():
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(type="freelancer"))


def test_contract_negative_salary_rejected():
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(base_monthly_salary=Decimal("-1")))


def test_contract_weekly_hours_must_be_positive():
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(weekly_hours=Decimal("0")))


def test_contract_fte_percent_in_range():
    Contract(**_valid_contract_kwargs(fte_percent=Decimal("0.5")))
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(fte_percent=Decimal("0")))
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(fte_percent=Decimal("1.5")))


def test_contract_end_before_start_rejected():
    with pytest.raises(ValidationError):
        Contract(**_valid_contract_kwargs(
            start_date=_date(2025, 6, 1),
            end_date=_date(2025, 5, 1),
        ))


def test_employee_basic():
    e = Employee(
        employee_id="e-1",
        full_name="Maria Santos",
        tax_id="123456789",
        social_security_id="11122233344",
        birth_date=_date(1990, 1, 1),
        hire_date=_date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="solteiro_sem_dependentes"),
    )
    assert e.status == "active"


def test_employee_status_enum():
    with pytest.raises(ValidationError):
        Employee(
            employee_id="e-1", full_name="x", tax_id="x", social_security_id="x",
            birth_date=_date(1990, 1, 1), hire_date=_date(2025, 1, 1),
            fiscal_profile=FiscalProfile(irs_table_code="x"),
            status="vacation",
        )


def test_compensation_package_default_empty():
    pkg = CompensationPackage(contract_id="c-1")
    assert pkg.entitlements == []


def test_compensation_entitlement_arbitrary_parameters():
    ent = CompensationEntitlement(component_code="meal_allowance", parameters={"daily_rate": "6.00"})
    assert ent.parameters["daily_rate"] == "6.00"
