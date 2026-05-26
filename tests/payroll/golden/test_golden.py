# tests/payroll/golden/test_golden.py
from datetime import date, datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
from logic.payroll.public.service import PayrollService
from logic.payroll.public.schemas import (
    CreateEmployeeInput, CreateContractInput, FiscalProfile, PeriodDefinition,
    TimeInputDraft,
)
from logic.payroll.primitives.base import DEFAULT_REGISTRY
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.clock import FixedClock
from db.repositories.memory import (
    InMemoryEmployeeRepository, InMemoryContractRepository,
    InMemoryPeriodRepository, InMemoryTimeInputRepository,
    InMemoryPayslipRepository,
)


def _decimal_loads(text: str):
    return json.loads(text, parse_float=Decimal)


def test_golden_scenario(scenario_dir: Path):
    statutory = scenario_dir / "statutory.yaml"
    company = scenario_dir / "company.yaml"
    inputs = _decimal_loads((scenario_dir / "inputs.json").read_text(encoding="utf-8"))
    expected = _decimal_loads((scenario_dir / "expected_payslip.json").read_text(encoding="utf-8"))

    clock_iso = inputs["clock"]
    clock = FixedClock(datetime.fromisoformat(clock_iso))

    service = PayrollService(
        employee_repo=InMemoryEmployeeRepository(),
        contract_repo=InMemoryContractRepository(),
        period_repo=InMemoryPeriodRepository(),
        time_input_repo=InMemoryTimeInputRepository(),
        payslip_repo=InMemoryPayslipRepository(),
        rule_loader=RuleLoader(),
        primitive_registry=DEFAULT_REGISTRY,
        clock=clock,
        statutory_path=statutory,
        company_path=company,
    )

    emp = inputs["employee"]
    service.create_employee(CreateEmployeeInput(
        employee_id=emp["employee_id"], full_name=emp["full_name"],
        tax_id=emp["tax_id"], social_security_id=emp["social_security_id"],
        birth_date=date.fromisoformat(emp["birth_date"]),
        hire_date=date.fromisoformat(emp["hire_date"]),
        fiscal_profile=FiscalProfile(**emp["fiscal_profile"]),
    ))
    con = inputs["contract"]
    service.create_contract(CreateContractInput(
        contract_id=con["contract_id"], employee_id=con["employee_id"],
        type=con["type"], start_date=date.fromisoformat(con["start_date"]),
        role_category=con["role_category"],
        weekly_hours=Decimal(con["weekly_hours"]),
        fte_percent=Decimal(con["fte_percent"]),
        base_monthly_salary=Decimal(con["base_monthly_salary"]),
        company_id=con["company_id"],
    ))
    per = inputs["period"]
    service.open_period(per["company_id"], PeriodDefinition(
        period_id=per["period_id"], pay_frequency=per["pay_frequency"],
        start_date=date.fromisoformat(per["start_date"]),
        end_date=date.fromisoformat(per["end_date"]),
        pay_date=date.fromisoformat(per["pay_date"]),
    ))
    ti = inputs["time_input"]
    service.set_time_input(per["period_id"], emp["employee_id"], TimeInputDraft(
        normal_hours=Decimal(ti["normal_hours"]),
        meal_allowance_days=ti.get("meal_allowance_days", 0),
    ))

    result = service.dry_run_payslip(per["period_id"], emp["employee_id"])

    # Compare structured fields with the expected JSON
    assert result.net_pay == Decimal(expected["net_pay"])
    assert len(result.gross_earnings) == len(expected["gross_earnings"])
    for got, exp in zip(result.gross_earnings, expected["gross_earnings"]):
        assert got.component_code == exp["component_code"]
        assert got.amount == Decimal(exp["amount"])
        assert got.tax_treatment == exp["tax_treatment"]
    assert len(result.deductions) == len(expected["deductions"])
    for got, exp in zip(result.deductions, expected["deductions"]):
        assert got.component_code == exp["component_code"]
        assert got.amount == Decimal(exp["amount"])
