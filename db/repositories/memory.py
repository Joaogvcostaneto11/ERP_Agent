from __future__ import annotations
from typing import Optional
from logic.payroll.public.schemas import (
    Employee, Contract, PayrollPeriod, TimeInput, PayslipResult,
)


class InMemoryEmployeeRepository:
    def __init__(self) -> None:
        self._store: dict[str, Employee] = {}

    def upsert(self, employee: Employee) -> Employee:
        self._store[employee.employee_id] = employee
        return employee

    def get(self, employee_id: str) -> Optional[Employee]:
        return self._store.get(employee_id)


class InMemoryContractRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, Contract] = {}
        self._by_employee: dict[str, Contract] = {}

    def upsert(self, contract: Contract) -> Contract:
        self._by_id[contract.contract_id] = contract
        self._by_employee[contract.employee_id] = contract
        return contract

    def get(self, contract_id: str) -> Optional[Contract]:
        return self._by_id.get(contract_id)

    def get_for_employee(self, employee_id: str) -> Optional[Contract]:
        return self._by_employee.get(employee_id)


class InMemoryPeriodRepository:
    def __init__(self) -> None:
        self._store: dict[str, PayrollPeriod] = {}

    def upsert(self, period: PayrollPeriod) -> PayrollPeriod:
        self._store[period.period_id] = period
        return period

    def get(self, period_id: str) -> Optional[PayrollPeriod]:
        return self._store.get(period_id)


class InMemoryTimeInputRepository:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], TimeInput] = {}

    def upsert(self, time_input: TimeInput) -> TimeInput:
        self._store[(time_input.period_id, time_input.employee_id)] = time_input
        return time_input

    def get(self, period_id: str, employee_id: str) -> Optional[TimeInput]:
        return self._store.get((period_id, employee_id))


class InMemoryPayslipRepository:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], PayslipResult] = {}

    def upsert(self, payslip: PayslipResult) -> PayslipResult:
        self._store[(payslip.period_id, payslip.employee_id)] = payslip
        return payslip

    def get(self, period_id: str, employee_id: str) -> Optional[PayslipResult]:
        return self._store.get((period_id, employee_id))
