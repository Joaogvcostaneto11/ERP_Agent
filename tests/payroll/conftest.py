# tests/payroll/conftest.py
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, Company, PayrollPeriod,
)
from logic.payroll.primitives.base import ExecutionContext
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.clock import FixedClock


@pytest.fixture
def fixed_clock():
    return FixedClock(datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc))


@pytest.fixture
def default_company():
    return Company(
        company_id="acme",
        legal_name="Acme, Lda.",
        tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )


@pytest.fixture
def default_period():
    return PayrollPeriod(
        period_id="2026-05",
        company_id="acme",
        pay_frequency="monthly",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )


@pytest.fixture
def default_employee():
    return Employee(
        employee_id="e-1",
        full_name="Maria Santos",
        tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1),
        hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="solteiro_sem_dependentes"),
    )


@pytest.fixture
def default_contract():
    return Contract(
        contract_id="c-1",
        employee_id="e-1",
        type="CT",
        start_date=date(2025, 1, 1),
        role_category="developer",
        weekly_hours=Decimal("40"),
        fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"),
        company_id="acme",
    )


@pytest.fixture
def default_context(default_period, default_employee, default_contract, default_company, fixed_clock):
    return ExecutionContext(
        period=default_period,
        contract=default_contract,
        employee=default_employee,
        company=default_company,
        rounding_policy=RoundingPolicy(),
        clock=fixed_clock,
    )
