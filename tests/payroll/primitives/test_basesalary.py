from datetime import date, datetime, timezone
from decimal import Decimal
from logic.payroll.primitives.basesalary import BaseSalary, BaseSalaryParams, BaseSalaryInputs
from logic.payroll.primitives.base import ExecutionContext
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.clock import FixedClock
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, Company, PayrollPeriod,
)


def _ctx(salary: Decimal = Decimal("1500")) -> ExecutionContext:
    company = Company(
        company_id="acme", legal_name="Acme", tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )
    employee = Employee(
        employee_id="e-1", full_name="Maria", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    )
    contract = Contract(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=salary, company_id="acme",
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


def test_base_salary_returns_contract_amount():
    prim = BaseSalary()
    result = prim.execute(BaseSalaryParams(), BaseSalaryInputs(), _ctx(Decimal("1500")))
    assert result.amount == Decimal("1500.00")
    assert result.tax_treatment == "taxable"


def test_base_salary_is_rounded_to_two_places():
    prim = BaseSalary()
    result = prim.execute(BaseSalaryParams(), BaseSalaryInputs(), _ctx(Decimal("1500.005")))
    assert result.amount == Decimal("1500.01")


def test_base_salary_metadata_attributes():
    assert BaseSalary.name == "BaseSalary"
    assert BaseSalary.parameter_schema is BaseSalaryParams
    assert BaseSalary.input_schema is BaseSalaryInputs
