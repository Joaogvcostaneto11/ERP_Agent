from datetime import date

import pytest

from logic.payroll.models import Employee, EmployeeType, PayPeriod, PayrollRunRequest, TimeRecord
from logic.payroll.validator import (
    validate_employee,
    validate_minimum_wage,
    validate_role_permission,
    validate_run_request,
    validate_time_record,
)


@pytest.fixture
def salaried():
    return Employee(
        id="e1", name="Alice", type=EmployeeType.salaried,
        pay_period=PayPeriod.monthly, annual_salary=50_000.0,
    )


@pytest.fixture
def hourly():
    return Employee(
        id="e2", name="Bob", type=EmployeeType.hourly,
        pay_period=PayPeriod.weekly, hourly_rate=20.0,
    )


@pytest.fixture
def contractor():
    return Employee(
        id="e3", name="Charlie", type=EmployeeType.contractor,
        pay_period=PayPeriod.monthly,
    )


@pytest.fixture
def base_period():
    return (date(2026, 5, 1), date(2026, 5, 31))


# ── Employee validation ──────────────────────────────────────────────────────

def test_contractor_blocked(contractor):
    errors = validate_employee(contractor)
    assert any("Contractors" in e for e in errors)


def test_salaried_passes(salaried):
    assert validate_employee(salaried) == []


def test_hourly_passes(hourly):
    assert validate_employee(hourly) == []


# ── Time record validation ───────────────────────────────────────────────────

def test_unapproved_time_record_blocked(hourly, base_period):
    tr = TimeRecord(
        employee_id="e2",
        period_start=base_period[0], period_end=base_period[1],
        regular_hours=40.0, approved=False,
    )
    errors = validate_time_record(tr, hourly)
    assert any("approved" in e for e in errors)


def test_approved_time_record_passes(hourly, base_period):
    tr = TimeRecord(
        employee_id="e2",
        period_start=base_period[0], period_end=base_period[1],
        regular_hours=40.0, approved=True, approved_by="mgr",
    )
    assert validate_time_record(tr, hourly) == []


def test_negative_hours_blocked(hourly, base_period):
    tr = TimeRecord(
        employee_id="e2",
        period_start=base_period[0], period_end=base_period[1],
        regular_hours=-1.0, approved=True,
    )
    errors = validate_time_record(tr, hourly)
    assert any("non-negative" in e for e in errors)


def test_salaried_time_record_not_required(salaried, base_period):
    tr = TimeRecord(
        employee_id="e1",
        period_start=base_period[0], period_end=base_period[1],
        regular_hours=160.0, approved=False,
    )
    # Salaried employees do not need an approved time record
    assert validate_time_record(tr, salaried) == []


# ── Run request validation ───────────────────────────────────────────────────

def test_inverted_period_blocked():
    req = PayrollRunRequest(
        period_start=date(2026, 5, 31), period_end=date(2026, 5, 1),
        employee_ids=["e1"], initiated_by="hr1",
    )
    errors = validate_run_request(req, [])
    assert any("period_end" in e for e in errors)


def test_duplicate_employee_blocked():
    req = PayrollRunRequest(
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
        employee_ids=["e1", "e1"], initiated_by="hr1",
    )
    errors = validate_run_request(req, [])
    assert any("more than once" in e for e in errors)


def test_valid_run_request_passes():
    req = PayrollRunRequest(
        period_start=date(2026, 5, 1), period_end=date(2026, 5, 31),
        employee_ids=["e1", "e2"], initiated_by="hr1",
    )
    assert validate_run_request(req, []) == []


# ── Minimum wage ─────────────────────────────────────────────────────────────

def test_minimum_wage_violation():
    errors = validate_minimum_wage(net_pay=3.00, minimum_wage=500.0)
    assert any("minimum wage" in e for e in errors)


def test_minimum_wage_passes():
    assert validate_minimum_wage(net_pay=1_000.0, minimum_wage=500.0) == []


# ── Role permissions ─────────────────────────────────────────────────────────

def test_finance_director_can_approve():
    assert validate_role_permission("approve_payroll_run", "finance_director") == []


def test_employee_cannot_approve():
    errors = validate_role_permission("approve_payroll_run", "employee")
    assert any("not permitted" in e for e in errors)


def test_hr_manager_can_initiate():
    assert validate_role_permission("initiate_payroll_run", "hr_manager") == []


def test_auditor_can_view_all():
    assert validate_role_permission("view_all_payroll", "auditor") == []
