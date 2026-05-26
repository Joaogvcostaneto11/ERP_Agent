from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PayrollPeriod(BaseModel):
    model_config = ConfigDict(strict=True)

    period_id: str
    company_id: str
    pay_frequency: Literal["monthly", "biweekly", "weekly"]
    start_date: date
    end_date: date
    pay_date: date
    status: Literal["open", "calculated", "closed"] = "open"

    @model_validator(mode="after")
    def _check_dates(self) -> "PayrollPeriod":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class AbsenceEntry(BaseModel):
    model_config = ConfigDict(strict=True)

    start_date: date
    end_date: date
    code: str
    paid_percent: Optional[Decimal] = None

    @model_validator(mode="after")
    def _check_dates(self) -> "AbsenceEntry":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be >= start_date")
        return self


class OvertimeBuckets(BaseModel):
    model_config = ConfigDict(strict=True)

    first_hour: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))
    additional_hours: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))
    weekend: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))
    holiday: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))
    night: Decimal = Field(ge=Decimal("0"), default=Decimal("0"))


class TimeInput(BaseModel):
    model_config = ConfigDict(strict=True)

    period_id: str
    employee_id: str
    normal_hours: Decimal = Field(ge=Decimal("0"))
    overtime_buckets: OvertimeBuckets = Field(default_factory=OvertimeBuckets)
    absences: list[AbsenceEntry] = Field(default_factory=list)
    meal_allowance_days: int = Field(ge=0, default=0)
    notes: str = ""
