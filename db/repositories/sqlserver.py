from __future__ import annotations
from typing import Optional

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models import (
    ContractRow, EmployeeRow, PayrollPeriodRow, PayslipRow, TimeInputRow,
)
from logic.payroll.public.schemas import (
    Contract, Employee, PayrollPeriod, PayslipResult, TimeInput,
)
from logic.payroll.public.schemas.identity import CCTReference, FiscalProfile
from logic.payroll.public.schemas.output import AuditTrailEntry, PayslipLine
from logic.payroll.public.schemas.period import AbsenceEntry, OvertimeBuckets

_absence_adapter = TypeAdapter(list[AbsenceEntry])
_audit_adapter = TypeAdapter(list[AuditTrailEntry])
_payslip_line_adapter = TypeAdapter(list[PayslipLine])


class SqlServerEmployeeRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, employee: Employee) -> Employee:
        fp_json = employee.fiscal_profile.model_dump_json()
        row = self._s.get(EmployeeRow, employee.employee_id)
        if row is None:
            self._s.add(EmployeeRow(
                employee_id=employee.employee_id,
                full_name=employee.full_name,
                tax_id=employee.tax_id,
                social_security_id=employee.social_security_id,
                birth_date=employee.birth_date,
                hire_date=employee.hire_date,
                status=employee.status,
                fiscal_profile=fp_json,
                current_contract_id=employee.current_contract_id,
                bank_iban=employee.bank_iban,
            ))
        else:
            row.full_name = employee.full_name
            row.tax_id = employee.tax_id
            row.social_security_id = employee.social_security_id
            row.birth_date = employee.birth_date
            row.hire_date = employee.hire_date
            row.status = employee.status
            row.fiscal_profile = fp_json
            row.current_contract_id = employee.current_contract_id
            row.bank_iban = employee.bank_iban
        self._s.flush()
        return employee

    def get(self, employee_id: str) -> Optional[Employee]:
        row = self._s.get(EmployeeRow, employee_id)
        if row is None:
            return None
        return Employee.model_validate({
            "employee_id": row.employee_id,
            "full_name": row.full_name,
            "tax_id": row.tax_id,
            "social_security_id": row.social_security_id,
            "birth_date": row.birth_date,
            "hire_date": row.hire_date,
            "status": row.status,
            "fiscal_profile": FiscalProfile.model_validate_json(row.fiscal_profile),
            "current_contract_id": row.current_contract_id,
            "bank_iban": row.bank_iban,
        }, strict=False)


class SqlServerContractRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, contract: Contract) -> Contract:
        cct_json = contract.cct_reference.model_dump_json() if contract.cct_reference else None
        row = self._s.get(ContractRow, contract.contract_id)
        if row is None:
            self._s.add(ContractRow(
                contract_id=contract.contract_id,
                employee_id=contract.employee_id,
                type=contract.type,
                start_date=contract.start_date,
                end_date=contract.end_date,
                role_category=contract.role_category,
                weekly_hours=contract.weekly_hours,
                fte_percent=contract.fte_percent,
                base_monthly_salary=contract.base_monthly_salary,
                cct_reference=cct_json,
                company_id=contract.company_id,
                pay_frequency=contract.pay_frequency,
            ))
        else:
            row.employee_id = contract.employee_id
            row.type = contract.type
            row.start_date = contract.start_date
            row.end_date = contract.end_date
            row.role_category = contract.role_category
            row.weekly_hours = contract.weekly_hours
            row.fte_percent = contract.fte_percent
            row.base_monthly_salary = contract.base_monthly_salary
            row.cct_reference = cct_json
            row.company_id = contract.company_id
            row.pay_frequency = contract.pay_frequency
        self._s.flush()
        return contract

    def get(self, contract_id: str) -> Optional[Contract]:
        row = self._s.get(ContractRow, contract_id)
        return _row_to_contract(row) if row else None

    def get_for_employee(self, employee_id: str) -> Optional[Contract]:
        row = self._s.execute(
            select(ContractRow).where(ContractRow.employee_id == employee_id)
        ).scalar_one_or_none()
        return _row_to_contract(row) if row else None


def _row_to_contract(row: ContractRow) -> Contract:
    cct = CCTReference.model_validate_json(row.cct_reference) if row.cct_reference else None
    return Contract.model_validate({
        "contract_id": row.contract_id,
        "employee_id": row.employee_id,
        "type": row.type,
        "start_date": row.start_date,
        "end_date": row.end_date,
        "role_category": row.role_category,
        "weekly_hours": row.weekly_hours,
        "fte_percent": row.fte_percent,
        "base_monthly_salary": row.base_monthly_salary,
        "cct_reference": cct,
        "company_id": row.company_id,
        "pay_frequency": row.pay_frequency,
    }, strict=False)


class SqlServerPeriodRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, period: PayrollPeriod) -> PayrollPeriod:
        row = self._s.get(PayrollPeriodRow, period.period_id)
        if row is None:
            self._s.add(PayrollPeriodRow(
                period_id=period.period_id,
                company_id=period.company_id,
                pay_frequency=period.pay_frequency,
                start_date=period.start_date,
                end_date=period.end_date,
                pay_date=period.pay_date,
                status=period.status,
            ))
        else:
            row.company_id = period.company_id
            row.pay_frequency = period.pay_frequency
            row.start_date = period.start_date
            row.end_date = period.end_date
            row.pay_date = period.pay_date
            row.status = period.status
        self._s.flush()
        return period

    def get(self, period_id: str) -> Optional[PayrollPeriod]:
        row = self._s.get(PayrollPeriodRow, period_id)
        if row is None:
            return None
        return PayrollPeriod.model_validate({
            "period_id": row.period_id,
            "company_id": row.company_id,
            "pay_frequency": row.pay_frequency,
            "start_date": row.start_date,
            "end_date": row.end_date,
            "pay_date": row.pay_date,
            "status": row.status,
        }, strict=False)


class SqlServerTimeInputRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, time_input: TimeInput) -> TimeInput:
        ot_json = time_input.overtime_buckets.model_dump_json()
        abs_json = _absence_adapter.dump_json(time_input.absences).decode()
        row = self._s.get(TimeInputRow, (time_input.period_id, time_input.employee_id))
        if row is None:
            self._s.add(TimeInputRow(
                period_id=time_input.period_id,
                employee_id=time_input.employee_id,
                normal_hours=time_input.normal_hours,
                overtime_buckets=ot_json,
                absences=abs_json,
                meal_allowance_days=time_input.meal_allowance_days,
                notes=time_input.notes,
            ))
        else:
            row.normal_hours = time_input.normal_hours
            row.overtime_buckets = ot_json
            row.absences = abs_json
            row.meal_allowance_days = time_input.meal_allowance_days
            row.notes = time_input.notes
        self._s.flush()
        return time_input

    def get(self, period_id: str, employee_id: str) -> Optional[TimeInput]:
        row = self._s.get(TimeInputRow, (period_id, employee_id))
        if row is None:
            return None
        return TimeInput.model_validate({
            "period_id": row.period_id,
            "employee_id": row.employee_id,
            "normal_hours": row.normal_hours,
            "overtime_buckets": OvertimeBuckets.model_validate_json(row.overtime_buckets),
            "absences": _absence_adapter.validate_json(row.absences),
            "meal_allowance_days": row.meal_allowance_days,
            "notes": row.notes,
        }, strict=False)


class SqlServerPayslipRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, payslip: PayslipResult) -> PayslipResult:
        gross_json = _payslip_line_adapter.dump_json(payslip.gross_earnings).decode()
        ded_json = _payslip_line_adapter.dump_json(payslip.deductions).decode()
        emp_json = _payslip_line_adapter.dump_json(payslip.employer_contributions).decode()
        audit_json = _audit_adapter.dump_json(payslip.audit).decode()
        row = self._s.get(PayslipRow, (payslip.period_id, payslip.employee_id))
        if row is None:
            self._s.add(PayslipRow(
                period_id=payslip.period_id,
                employee_id=payslip.employee_id,
                gross_earnings=gross_json,
                deductions=ded_json,
                employer_contributions=emp_json,
                net_pay=payslip.net_pay,
                audit=audit_json,
            ))
        else:
            row.gross_earnings = gross_json
            row.deductions = ded_json
            row.employer_contributions = emp_json
            row.net_pay = payslip.net_pay
            row.audit = audit_json
        self._s.flush()
        return payslip

    def get(self, period_id: str, employee_id: str) -> Optional[PayslipResult]:
        row = self._s.get(PayslipRow, (period_id, employee_id))
        if row is None:
            return None
        return PayslipResult.model_validate({
            "period_id": row.period_id,
            "employee_id": row.employee_id,
            "gross_earnings": _payslip_line_adapter.validate_json(row.gross_earnings),
            "deductions": _payslip_line_adapter.validate_json(row.deductions),
            "employer_contributions": _payslip_line_adapter.validate_json(row.employer_contributions),
            "net_pay": row.net_pay,
            "audit": _audit_adapter.validate_json(row.audit),
        }, strict=False)
