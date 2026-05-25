from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, model_validator


class EmployeeType(str, Enum):
    salaried = "salaried"
    hourly = "hourly"
    contractor = "contractor"


class PayPeriod(str, Enum):
    weekly = "weekly"
    biweekly = "biweekly"
    monthly = "monthly"


class Employee(BaseModel):
    id: str
    name: str
    type: EmployeeType
    pay_period: PayPeriod
    annual_salary: Optional[float] = None
    hourly_rate: Optional[float] = None
    deduction_elections: list[str] = []

    @model_validator(mode="after")
    def _check_compensation(self) -> Employee:
        if self.type == EmployeeType.salaried and self.annual_salary is None:
            raise ValueError("Salaried employees require annual_salary")
        if self.type == EmployeeType.hourly and self.hourly_rate is None:
            raise ValueError("Hourly employees require hourly_rate")
        return self


class TimeRecord(BaseModel):
    employee_id: str
    period_start: date
    period_end: date
    regular_hours: float
    overtime_hours: float = 0.0
    approved: bool = False
    approved_by: Optional[str] = None


class PayslipLine(BaseModel):
    description: str
    amount: float
    type: Literal["earning", "deduction"]


class Payslip(BaseModel):
    employee_id: str
    period_start: date
    period_end: date
    run_id: str
    gross_pay: float
    total_deductions: float
    net_pay: float
    lines: list[PayslipLine]
    rule_version: str


class RunStatus(str, Enum):
    collect = "collect"
    calculate = "calculate"
    review = "review"
    committed = "committed"
    disbursed = "disbursed"


class PayrollRunRequest(BaseModel):
    period_start: date
    period_end: date
    employee_ids: list[str]
    initiated_by: str


class RunInitiateBody(BaseModel):
    run: PayrollRunRequest
    employees: list[Employee]
    time_records: list[TimeRecord] = []


class PayrollRun(BaseModel):
    id: str
    status: RunStatus
    period_start: date
    period_end: date
    initiated_by: str
    approved_by: Optional[str] = None
    payslips: list[Payslip] = []
    rule_version: str = "1.0.0"


class ApproveBody(BaseModel):
    approved_by: str
    role: str


class AdjustmentRequest(BaseModel):
    original_run_id: str
    employee_id: str
    reason: str
    delta_gross: float
    requested_by: str


class AdjustmentBody(BaseModel):
    adjustment: AdjustmentRequest
    role: str


class IntentRequest(BaseModel):
    text: str
    user_id: str
    role: str
    context: dict = {}


class ConverseRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    user_id: str
    role: str


class ConverseResponse(BaseModel):
    session_id: str
    reply: str
    action_taken: Optional[dict] = None
