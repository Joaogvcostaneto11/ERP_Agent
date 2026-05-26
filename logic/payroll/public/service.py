from __future__ import annotations
from pathlib import Path
from typing import Optional
from logic.payroll.errors import MissingInput
from logic.payroll.public.schemas import (
    Employee, Contract, FiscalProfile, PayrollPeriod, TimeInput,
    CreateEmployeeInput, CreateContractInput, PeriodDefinition,
    TimeInputDraft, PayslipResult,
)
from logic.payroll.primitives.base import PrimitiveRegistry
from logic.payroll.rules.loader import RuleLoader
from logic.payroll.clock import Clock
from db.repositories.interfaces import (
    EmployeeRepository, ContractRepository, PeriodRepository,
    TimeInputRepository, PayslipRepository,
)


class PayrollService:
    def __init__(
        self,
        employee_repo: EmployeeRepository,
        contract_repo: ContractRepository,
        period_repo: PeriodRepository,
        time_input_repo: TimeInputRepository,
        payslip_repo: PayslipRepository,
        rule_loader: RuleLoader,
        primitive_registry: PrimitiveRegistry,
        clock: Clock,
        statutory_path: Path,
        company_path: Optional[Path] = None,
        cct_path: Optional[Path] = None,
    ) -> None:
        self._employees = employee_repo
        self._contracts = contract_repo
        self._periods = period_repo
        self._time_inputs = time_input_repo
        self._payslips = payslip_repo
        self._rule_loader = rule_loader
        self._registry = primitive_registry
        self._clock = clock
        self._statutory_path = statutory_path
        self._company_path = company_path
        self._cct_path = cct_path

    # --- Registry ---

    def create_employee(self, input: CreateEmployeeInput) -> Employee:
        employee = Employee(
            employee_id=input.employee_id,
            full_name=input.full_name,
            tax_id=input.tax_id,
            social_security_id=input.social_security_id,
            birth_date=input.birth_date,
            hire_date=input.hire_date,
            status="active",
            fiscal_profile=input.fiscal_profile,
            bank_iban=input.bank_iban,
        )
        return self._employees.upsert(employee)

    def get_employee(self, employee_id: str) -> Employee:
        e = self._employees.get(employee_id)
        if e is None:
            raise MissingInput(
                code="EMPLOYEE_NOT_FOUND",
                msg_pt=f"colaborador {employee_id!r} não encontrado",
                msg_en=f"employee {employee_id!r} not found",
            )
        return e

    def create_contract(self, input: CreateContractInput) -> Contract:
        # Ensure employee exists
        self.get_employee(input.employee_id)
        contract = Contract(
            contract_id=input.contract_id,
            employee_id=input.employee_id,
            type=input.type,
            start_date=input.start_date,
            end_date=input.end_date,
            role_category=input.role_category,
            weekly_hours=input.weekly_hours,
            fte_percent=input.fte_percent,
            base_monthly_salary=input.base_monthly_salary,
            cct_reference=input.cct_reference,
            company_id=input.company_id,
            pay_frequency=input.pay_frequency,
        )
        saved = self._contracts.upsert(contract)
        # Update employee current_contract_id
        employee = self.get_employee(input.employee_id)
        updated = employee.model_copy(update={"current_contract_id": saved.contract_id})
        self._employees.upsert(updated)
        return saved

    def get_contract_for_employee(self, employee_id: str) -> Contract:
        c = self._contracts.get_for_employee(employee_id)
        if c is None:
            raise MissingInput(
                code="CONTRACT_NOT_FOUND",
                msg_pt=f"contrato para colaborador {employee_id!r} não encontrado",
                msg_en=f"no contract for employee {employee_id!r}",
            )
        return c

    # --- Period management ---

    def open_period(self, company_id: str, definition: PeriodDefinition) -> PayrollPeriod:
        period = PayrollPeriod(
            period_id=definition.period_id,
            company_id=company_id,
            pay_frequency=definition.pay_frequency,
            start_date=definition.start_date,
            end_date=definition.end_date,
            pay_date=definition.pay_date,
            status="open",
        )
        return self._periods.upsert(period)

    def get_period(self, period_id: str) -> PayrollPeriod:
        p = self._periods.get(period_id)
        if p is None:
            raise MissingInput(
                code="PERIOD_NOT_FOUND",
                msg_pt=f"período {period_id!r} não encontrado",
                msg_en=f"period {period_id!r} not found",
            )
        return p

    # --- Time / attendance ---

    def set_time_input(self, period_id: str, employee_id: str, draft: TimeInputDraft) -> TimeInput:
        self.get_period(period_id)
        self.get_employee(employee_id)
        ti = TimeInput(
            period_id=period_id,
            employee_id=employee_id,
            normal_hours=draft.normal_hours,
            meal_allowance_days=draft.meal_allowance_days,
            notes=draft.notes,
        )
        return self._time_inputs.upsert(ti)

    def get_time_input(self, period_id: str, employee_id: str) -> TimeInput:
        ti = self._time_inputs.get(period_id, employee_id)
        if ti is None:
            raise MissingInput(
                code="TIME_INPUT_NOT_FOUND",
                msg_pt=f"sem dados de tempo para colaborador {employee_id!r} no período {period_id!r}",
                msg_en=f"no time input for employee {employee_id!r} in period {period_id!r}",
            )
        return ti
