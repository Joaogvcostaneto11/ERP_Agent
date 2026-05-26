from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
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
