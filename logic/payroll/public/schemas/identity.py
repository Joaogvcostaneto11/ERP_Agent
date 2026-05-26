from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator
from logic.payroll.primitives.rounding import RoundingPolicy


class FiscalProfile(BaseModel):
    model_config = ConfigDict(strict=True)

    irs_table_code: str
    dependents: int = Field(ge=0, default=0)
    has_disability: bool = False
    spouse_has_disability: bool = False
    residency_status: Literal["resident", "non_habitual_resident", "non_resident"] = "resident"
    voluntary_irs_rate: Optional[Decimal] = None


class CCTReference(BaseModel):
    model_config = ConfigDict(strict=True)

    cct_id: str
    cct_version: str
    role_category_code: str


class Company(BaseModel):
    model_config = ConfigDict(strict=True)

    company_id: str
    legal_name: str
    tax_id: str
    default_rounding_policy: RoundingPolicy
    default_subsidio_payment_mode: Literal["one_shot", "duodecimos"] = "duodecimos"


class Contract(BaseModel):
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

    @model_validator(mode="after")
    def _check_dates(self) -> "Contract":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class Employee(BaseModel):
    model_config = ConfigDict(strict=True)

    employee_id: str
    full_name: str
    tax_id: str
    social_security_id: str
    birth_date: date
    hire_date: date
    status: Literal["active", "suspended", "terminated"] = "active"
    fiscal_profile: FiscalProfile
    current_contract_id: Optional[str] = None
    bank_iban: Optional[str] = None


class CompensationEntitlement(BaseModel):
    model_config = ConfigDict(strict=True)

    component_code: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class CompensationPackage(BaseModel):
    model_config = ConfigDict(strict=True)

    contract_id: str
    entitlements: list[CompensationEntitlement] = Field(default_factory=list)
