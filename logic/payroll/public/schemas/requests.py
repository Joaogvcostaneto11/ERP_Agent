from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from logic.payroll.public.schemas.identity import FiscalProfile, CCTReference


class CreateEmployeeInput(BaseModel):
    model_config = ConfigDict(strict=True)

    employee_id: str
    full_name: str
    tax_id: str
    social_security_id: str
    birth_date: date
    hire_date: date
    fiscal_profile: FiscalProfile
    bank_iban: Optional[str] = None


class CreateContractInput(BaseModel):
    model_config = ConfigDict(strict=True)

    contract_id: str
    employee_id: str
    type: Literal["CT", "CTT", "CTI", "part_time", "internship"]
    start_date: date
    end_date: Optional[date] = None
    role_category: str
    weekly_hours: Decimal = Field(gt=Decimal("0"))
    fte_percent: Decimal = Field(gt=Decimal("0"), le=Decimal("1"))
    base_monthly_salary: Decimal = Field(ge=Decimal("0"))
    cct_reference: Optional[CCTReference] = None
    company_id: str
    pay_frequency: Literal["monthly", "biweekly", "weekly"] = "monthly"


class PeriodDefinition(BaseModel):
    model_config = ConfigDict(strict=True)

    period_id: str
    pay_frequency: Literal["monthly", "biweekly", "weekly"] = "monthly"
    start_date: date
    end_date: date
    pay_date: date


class TimeInputDraft(BaseModel):
    model_config = ConfigDict(strict=True)

    normal_hours: Decimal = Field(ge=Decimal("0"))
    meal_allowance_days: int = Field(ge=0, default=0)
    notes: str = ""
