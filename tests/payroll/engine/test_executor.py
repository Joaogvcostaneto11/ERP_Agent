from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from logic.payroll.engine.executor import Executor
from logic.payroll.rules.plan import CalculationPlan, PlanStep
from logic.payroll.primitives.base import ExecutionContext, DEFAULT_REGISTRY
from logic.payroll.rounding import RoundingPolicy
from logic.payroll.clock import FixedClock
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, Company, PayrollPeriod,
    RuleCitation, TimeInput,
)


def _ctx(salary: Decimal = Decimal("1500")) -> ExecutionContext:
    company = Company(
        company_id="acme", legal_name="Acme", tax_id="500000000",
        default_rounding_policy=RoundingPolicy(),
    )
    employee = Employee(
        employee_id="e-1", full_name="Maria", tax_id="123456789",
        social_security_id="11122233344",
        birth_date=date(1990, 1, 1), hire_date=date(2025, 1, 1),
        fiscal_profile=FiscalProfile(irs_table_code="solteiro_sem_dependentes"),
    )
    contract = Contract(
        contract_id="c-1", employee_id="e-1", type="CT",
        start_date=date(2025, 1, 1), role_category="dev",
        weekly_hours=Decimal("40"), fte_percent=Decimal("1"),
        base_monthly_salary=salary, company_id="acme",
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


def _plan_base_plus_tsu() -> CalculationPlan:
    cit_base = RuleCitation(document_path="statutory.yaml", layer="statutory", clause="components.base_salary")
    cit_tsu = RuleCitation(document_path="statutory.yaml", layer="statutory", clause="components.tsu_employee")
    return CalculationPlan(
        employee_id="e-1", contract_id="c-1", period_id="2026-05", company_id="acme",
        rounding_policy=RoundingPolicy(),
        steps=[
            PlanStep(
                index=0, phase="gross", component_code="base_salary",
                primitive_name="BaseSalary", parameters={}, inputs_required=[],
                citations=[cit_base],
            ),
            PlanStep(
                index=1, phase="tax", component_code="tsu_employee",
                primitive_name="TSUContribution",
                parameters={"rate": "0.11", "base_components": ["base_salary"]},
                inputs_required=["base_salary"],
                citations=[cit_tsu],
            ),
        ],
    )


def test_executor_simple_base_plus_tsu():
    plan = _plan_base_plus_tsu()
    ctx = _ctx(Decimal("1500"))
    ti = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    executor = Executor(registry=DEFAULT_REGISTRY)
    result = executor.execute(plan=plan, context=ctx, time_input=ti)

    assert len(result.gross_earnings) == 1
    assert result.gross_earnings[0].amount == Decimal("1500.00")
    assert result.gross_earnings[0].tax_treatment == "taxable"

    assert len(result.deductions) == 1
    assert result.deductions[0].amount == Decimal("165.00")

    assert result.net_pay == Decimal("1335.00")
    assert len(result.audit) == 2
    assert result.audit[0].primitive == "BaseSalary"
    assert result.audit[1].primitive == "TSUContribution"


def test_executor_audit_entries_have_timestamps_and_citations():
    plan = _plan_base_plus_tsu()
    ctx = _ctx()
    ti = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    executor = Executor(registry=DEFAULT_REGISTRY)
    result = executor.execute(plan=plan, context=ctx, time_input=ti)

    for entry in result.audit:
        assert entry.timestamp == datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
        assert entry.rule_citation.layer == "statutory"


def test_executor_payslip_line_audit_refs_resolve():
    plan = _plan_base_plus_tsu()
    ctx = _ctx()
    ti = TimeInput(period_id="2026-05", employee_id="e-1", normal_hours=Decimal("160"))
    executor = Executor(registry=DEFAULT_REGISTRY)
    result = executor.execute(plan=plan, context=ctx, time_input=ti)
    for line in result.gross_earnings + result.deductions:
        assert 0 <= line.source_audit_ref < len(result.audit)
