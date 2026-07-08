from decimal import Decimal
from logic.payroll.engine.time_input import normalize_time_input
from logic.payroll.public.schemas import TimeInput


def test_normalize_passes_through_in_plan_1():
    ti = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    out = normalize_time_input(ti)
    assert out is ti  # Plan 1 is a no-op


def test_normalize_empty_meal_days_default():
    ti = TimeInput(period_id="p", employee_id="e", normal_hours=Decimal("0"))
    out = normalize_time_input(ti)
    assert out.meal_allowance_days == 0
