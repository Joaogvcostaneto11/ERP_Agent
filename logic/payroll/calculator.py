"""
Pure payroll math — no AI, no I/O, no side effects.
All rates are flat approximations; plug in tax-bracket tables when available.
"""
from typing import Optional

from logic.payroll.models import Employee, EmployeeType, PayPeriod, PayslipLine, TimeRecord

PERIODS_PER_YEAR: dict[PayPeriod, int] = {
    PayPeriod.weekly: 52,
    PayPeriod.biweekly: 26,
    PayPeriod.monthly: 12,
}

OVERTIME_MULTIPLIER = 1.5

_MANDATORY_RATES: dict[str, float] = {
    "income_tax": 0.20,
    "social_security": 0.08,
}

_OPTIONAL_RATES: dict[str, float] = {
    "health_insurance": 0.03,
    "retirement_plan": 0.05,
}


def gross_pay(employee: Employee, time_record: Optional[TimeRecord]) -> float:
    if employee.type == EmployeeType.contractor:
        raise ValueError("Contractors are not processed through standard payroll (payroll.yaml §employee_types)")
    if employee.type == EmployeeType.salaried:
        return employee.annual_salary / PERIODS_PER_YEAR[employee.pay_period]
    if time_record is None:
        raise ValueError(f"Time record required for hourly employee '{employee.id}'")
    regular = time_record.regular_hours * employee.hourly_rate
    overtime = time_record.overtime_hours * employee.hourly_rate * OVERTIME_MULTIPLIER
    return regular + overtime


def deduction_lines(gross: float, elections: list[str]) -> tuple[list[PayslipLine], float]:
    """
    Returns (lines, total_deductions).
    Mandatory deductions are applied before optional ones (payroll.yaml §deductions.rules).
    Raises if total exceeds gross.
    """
    lines: list[PayslipLine] = []
    total = 0.0

    for ded_id, rate in _MANDATORY_RATES.items():
        amount = round(gross * rate, 2)
        lines.append(PayslipLine(
            description=ded_id.replace("_", " ").title(),
            amount=amount,
            type="deduction",
        ))
        total += amount

    for ded_id, rate in _OPTIONAL_RATES.items():
        if ded_id in elections:
            amount = round(gross * rate, 2)
            lines.append(PayslipLine(
                description=ded_id.replace("_", " ").title(),
                amount=amount,
                type="deduction",
            ))
            total += amount

    total = round(total, 2)
    if total > gross:
        raise ValueError(
            f"Total deductions ({total}) exceed gross pay ({gross}) — payroll rejected "
            "(payroll.yaml §deductions.rules)"
        )
    return lines, total
