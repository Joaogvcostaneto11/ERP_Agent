from datetime import date
from decimal import Decimal
from db.repositories.memory import (
    InMemoryEmployeeRepository, InMemoryContractRepository,
    InMemoryPeriodRepository, InMemoryTimeInputRepository,
    InMemoryPayslipRepository,
)
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, PayrollPeriod, TimeInput,
    PayslipResult,
)


def _employee():
    return Employee(
        employee_id="e-1", full_name="Maria", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    )


def _contract():
    return Contract(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"), company_id="acme",
    )


def _period():
    return PayrollPeriod(
        period_id="2026-05", company_id="acme", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )


def test_employee_repo_upsert_then_get():
    repo = InMemoryEmployeeRepository()
    repo.upsert(_employee())
    e = repo.get("e-1")
    assert e is not None and e.employee_id == "e-1"


def test_employee_repo_missing_returns_none():
    repo = InMemoryEmployeeRepository()
    assert repo.get("nope") is None


def test_contract_repo_get_for_employee():
    repo = InMemoryContractRepository()
    repo.upsert(_contract())
    c = repo.get_for_employee("e-1")
    assert c is not None and c.contract_id == "c-1"


def test_period_repo_upsert_then_get():
    repo = InMemoryPeriodRepository()
    repo.upsert(_period())
    p = repo.get("2026-05")
    assert p is not None


def test_time_input_repo_keyed_by_period_and_employee():
    repo = InMemoryTimeInputRepository()
    ti = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    repo.upsert(ti)
    assert repo.get("2026-05", "e-1") is not None
    assert repo.get("2026-05", "other") is None


def test_payslip_repo_upsert_then_get():
    repo = InMemoryPayslipRepository()
    payslip = PayslipResult(period_id="2026-05", employee_id="e-1", net_pay=Decimal("1335"))
    repo.upsert(payslip)
    out = repo.get("2026-05", "e-1")
    assert out is not None and out.net_pay == Decimal("1335")
