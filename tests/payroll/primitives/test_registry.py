from datetime import date, datetime, timezone
from decimal import Decimal
import dataclasses
import pytest
from logic.payroll.primitives.base import (
    PrimitiveResult, ExecutionContext,
)
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, Company, PayrollPeriod,
)
from logic.payroll.primitives.rounding import RoundingPolicy
from logic.payroll.clock import FixedClock


def _make_context() -> ExecutionContext:
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


def test_primitive_result_minimal():
    r = PrimitiveResult(amount=Decimal("100"), tax_treatment="taxable")
    assert r.amount == Decimal("100")
    assert r.exempt_amount == Decimal("0")
    assert r.breakdown == []
    assert r.notes == ""


def test_execution_context_is_frozen():
    ctx = _make_context()
    assert dataclasses.is_dataclass(ctx)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.employee = None  # type: ignore
