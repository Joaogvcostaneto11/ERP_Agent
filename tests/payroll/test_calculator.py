from datetime import date

import pytest

from logic.payroll.calculator import deduction_lines, gross_pay
from logic.payroll.models import Employee, EmployeeType, PayPeriod, TimeRecord


@pytest.fixture
def salaried():
    return Employee(
        id="e1", name="Alice", type=EmployeeType.salaried,
        pay_period=PayPeriod.monthly, annual_salary=60_000.0,
    )


@pytest.fixture
def hourly():
    return Employee(
        id="e2", name="Bob", type=EmployeeType.hourly,
        pay_period=PayPeriod.weekly, hourly_rate=25.0,
        deduction_elections=["health_insurance"],
    )


@pytest.fixture
def time_record():
    return TimeRecord(
        employee_id="e2",
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 7),
        regular_hours=40.0, overtime_hours=5.0,
        approved=True, approved_by="manager1",
    )


def test_salaried_gross(salaried):
    # 60_000 / 12 = 5_000
    assert gross_pay(salaried, None) == pytest.approx(5_000.0)


def test_hourly_gross_no_overtime(hourly):
    tr = TimeRecord(
        employee_id="e2",
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 7),
        regular_hours=40.0, approved=True,
    )
    assert gross_pay(hourly, tr) == pytest.approx(1_000.0)


def test_hourly_gross_with_overtime(hourly, time_record):
    # 40 * 25 + 5 * 25 * 1.5 = 1_000 + 187.5 = 1_187.5
    assert gross_pay(hourly, time_record) == pytest.approx(1_187.5)


def test_hourly_requires_time_record(hourly):
    with pytest.raises(ValueError, match="Time record required"):
        gross_pay(hourly, None)


def test_contractor_rejected():
    contractor = Employee(
        id="e3", name="Charlie", type=EmployeeType.contractor,
        pay_period=PayPeriod.monthly,
    )
    with pytest.raises(ValueError, match="Contractors"):
        gross_pay(contractor, None)


def test_mandatory_deductions_always_applied(salaried):
    gross = 5_000.0
    lines, total = deduction_lines(gross, [])
    descriptions = {l.description for l in lines}
    assert "Income Tax" in descriptions
    assert "Social Security" in descriptions
    assert total == pytest.approx(gross * 0.28)  # 20% + 8%


def test_optional_deduction_added_when_elected(hourly):
    lines, total = deduction_lines(1_000.0, ["health_insurance"])
    assert any(l.description == "Health Insurance" for l in lines)


def test_optional_deduction_absent_when_not_elected():
    lines, _ = deduction_lines(1_000.0, [])
    assert not any(l.description == "Health Insurance" for l in lines)


def test_deductions_never_exceed_gross(monkeypatch):
    # Force a mandatory rate above 100% to verify the guard fires regardless of rate config
    import logic.payroll.calculator as calc_module
    monkeypatch.setitem(calc_module._MANDATORY_RATES, "income_tax", 1.5)
    with pytest.raises(ValueError, match="exceed gross"):
        deduction_lines(100.0, [])
