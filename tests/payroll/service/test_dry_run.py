# tests/payroll/service/test_dry_run.py
from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest
from logic.payroll.errors import MissingInput
from logic.payroll.public.service import PayrollService
from logic.payroll.public.schemas import (
    CreateEmployeeInput, CreateContractInput, FiscalProfile, PeriodDefinition,
    TimeInputDraft,
)
from logic.payroll.primitives.base import DEFAULT_REGISTRY
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.clock import FixedClock
from db.repositories.memory import (
    InMemoryEmployeeRepository, InMemoryContractRepository,
    InMemoryPeriodRepository, InMemoryTimeInputRepository,
    InMemoryPayslipRepository,
)
from datetime import datetime, timezone


@pytest.fixture
def service(tmp_path: Path):
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
    return PayrollService(
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


def test_create_employee_and_get(service):
    service.create_employee(CreateEmployeeInput(
        employee_id="e-1", full_name="Maria", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="solteiro_sem_dependentes"),
    ))
    e = service.get_employee("e-1")
    assert e.employee_id == "e-1"


def test_get_employee_missing_raises(service):
    with pytest.raises(MissingInput) as exc:
        service.get_employee("nope")
    assert exc.value.code == "EMPLOYEE_NOT_FOUND"


def test_create_contract_and_link(service):
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
    c = service.get_contract_for_employee("e-1")
    assert c.contract_id == "c-1"


def test_create_contract_without_employee_raises(service):
    with pytest.raises(MissingInput) as exc:
        service.create_contract(CreateContractInput(
            contract_id="c-1", employee_id="nope", type="CT",
            start_date=date(2025, 1, 1), role_category="dev",
            weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
            base_monthly_salary=Decimal("1500"), company_id="acme",
        ))
    assert exc.value.code == "EMPLOYEE_NOT_FOUND"
