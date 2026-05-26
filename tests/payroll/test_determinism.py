# tests/payroll/test_determinism.py
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import json
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


def _run_dry_run(statutory: Path, company: Path) -> dict:
    service = PayrollService(
        employee_repo=InMemoryEmployeeRepository(),
        contract_repo=InMemoryContractRepository(),
        period_repo=InMemoryPeriodRepository(),
        time_input_repo=InMemoryTimeInputRepository(),
        payslip_repo=InMemoryPayslipRepository(),
        rule_loader=RuleLoader(),
        primitive_registry=DEFAULT_REGISTRY,
        clock=FixedClock(datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)),
        statutory_path=statutory,
        company_path=company,
    )
    service.create_employee(CreateEmployeeInput(
        employee_id="e-1", full_name="x", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="x"),
    ))
    service.create_contract(CreateContractInput(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=Decimal("1500"), company_id="acme",
    ))
    service.open_period("acme", PeriodDefinition(
        period_id="2026-05", pay_frequency="monthly",
        start_date=date(2026, 5, 1), end_date=date(2026, 5, 31),
        pay_date=date(2026, 5, 31),
    ))
    service.set_time_input("2026-05", "e-1", TimeInputDraft(normal_hours=Decimal("160")))
    result = service.dry_run_payslip("2026-05", "e-1")
    return result.model_dump(mode="json")


def test_determinism_byte_identical_runs(tmp_path: Path):
    statutory = tmp_path / "statutory.yaml"
    statutory.write_text("""
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components:
  base_salary:
    type: earning
    phase: gross
    primitive: BaseSalary
    parameters: {}
    inputs_required: []
  tsu_employee:
    type: deduction
    phase: tax
    primitive: TSUContribution
    parameters:
      rate: "0.11"
      base_components: ["base_salary"]
    inputs_required: ["base_salary"]
""", encoding="utf-8")
    company = tmp_path / "company.yaml"
    company.write_text("""
metadata:
  jurisdiction: PT
  effective_from: "2026-01-01"
  version: "2026.1"
components: {}
""", encoding="utf-8")

    run1 = _run_dry_run(statutory, company)
    run2 = _run_dry_run(statutory, company)
    assert json.dumps(run1, sort_keys=True) == json.dumps(run2, sort_keys=True)
