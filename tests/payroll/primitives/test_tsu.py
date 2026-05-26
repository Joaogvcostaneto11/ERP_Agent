from datetime import date, datetime, timezone
from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.primitives.tsu import TSUContribution, TSUContributionParams, TSUContributionInputs
from logic.payroll.primitives.base import ExecutionContext
from logic.payroll.primitives.rounding import RoundingPolicy
from logic.payroll.clock import FixedClock
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, Company, PayrollPeriod,
)


def _ctx() -> ExecutionContext:
    company = Company(
        company_id="acme", legal_name="Acme", tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )
    employee = Employee(
        employee_id="e-1", full_name="x", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    )
    contract = Contract(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"), company_id="acme",
    )
    period = PayrollPeriod(
        period_id="2026-05", company_id="acme", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )
    return ExecutionContext(
        period=period, contract=contract, employee=employee, company=company,
        rounding_policy=RoundingPolicy(),
        clock=FixedClock(datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)),
    )


def test_tsu_employee_rate_applied_to_single_base_component():
    prim = TSUContribution()
    params = TSUContributionParams(rate=Decimal("0.11"), base_components=["base_salary"])
    inputs = TSUContributionInputs(component_values={"base_salary": Decimal("1500")})
    result = prim.execute(params, inputs, _ctx())
    assert result.amount == Decimal("165.00")
    assert result.tax_treatment == "taxable"


def test_tsu_sums_multiple_base_components():
    prim = TSUContribution()
    params = TSUContributionParams(rate=Decimal("0.11"), base_components=["base_salary", "diuturnidades"])
    inputs = TSUContributionInputs(component_values={
        "base_salary": Decimal("1500"),
        "diuturnidades": Decimal("100"),
    })
    result = prim.execute(params, inputs, _ctx())
    assert result.amount == Decimal("176.00")


def test_tsu_missing_input_raises():
    from logic.payroll.errors import MissingInput
    prim = TSUContribution()
    params = TSUContributionParams(rate=Decimal("0.11"), base_components=["base_salary"])
    inputs = TSUContributionInputs(component_values={})
    with pytest.raises(MissingInput) as exc:
        prim.execute(params, inputs, _ctx())
    assert exc.value.code == "TSU_MISSING_BASE_COMPONENT"


def test_tsu_rate_negative_rejected_at_param_validation():
    with pytest.raises(ValidationError):
        TSUContributionParams(rate=Decimal("-0.01"), base_components=["base_salary"])


def test_tsu_rate_above_one_rejected():
    with pytest.raises(ValidationError):
        TSUContributionParams(rate=Decimal("1.01"), base_components=["base_salary"])


def test_tsu_metadata():
    assert TSUContribution.name == "TSUContribution"
