from datetime import date
from decimal import Decimal
import pytest
from pydantic import ValidationError
from logic.payroll.public.schemas.period import (
    PayrollPeriod, AbsenceEntry, OvertimeBuckets, TimeInput,
)


def test_payroll_period_default_status_open():
    p = PayrollPeriod(
        period_id="2026-05",
        company_id="acme",
        pay_frequency="monthly",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    )
    assert p.status == "open"


def test_payroll_period_end_before_start_rejected():
    with pytest.raises(ValidationError):
        PayrollPeriod(
            period_id="x", company_id="acme", pay_frequency="monthly",
            start_date=date(2026, 5, 31), end_date=date(2026, 5, 1),
            pay_date=date(2026, 5, 31),
        )


def test_absence_entry_valid():
    a = AbsenceEntry(start_date=date(2026, 5, 10), end_date=date(2026, 5, 12), code="vacation")
    assert a.paid_percent is None


def test_absence_entry_end_before_start_rejected():
    with pytest.raises(ValidationError):
        AbsenceEntry(start_date=date(2026, 5, 12), end_date=date(2026, 5, 10), code="x")


def test_overtime_buckets_defaults_zero():
    b = OvertimeBuckets()
    assert b.first_hour == Decimal("0")
    assert b.weekend == Decimal("0")


def test_overtime_buckets_negative_rejected():
    with pytest.raises(ValidationError):
        OvertimeBuckets(first_hour=Decimal("-1"))


def test_time_input_defaults():
    t = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    assert t.overtime_buckets.first_hour == Decimal("0")
    assert t.absences == []
    assert t.meal_allowance_days == 0


def test_time_input_negative_normal_hours_rejected():
    with pytest.raises(ValidationError):
        TimeInput(period_id="p", employee_id="e", normal_hours=Decimal("-1"))


def test_time_input_negative_meal_days_rejected():
    with pytest.raises(ValidationError):
        TimeInput(period_id="p", employee_id="e", normal_hours=Decimal("0"), meal_allowance_days=-1)
