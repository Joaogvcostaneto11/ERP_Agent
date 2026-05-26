from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, Integer, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class EmployeeRow(Base):
    __tablename__ = "employees"

    employee_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    tax_id: Mapped[str] = mapped_column(String(20))
    social_security_id: Mapped[str] = mapped_column(String(20))
    birth_date: Mapped[date] = mapped_column(Date)
    hire_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    fiscal_profile: Mapped[str] = mapped_column(Text)  # JSON: FiscalProfile
    current_contract_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    bank_iban: Mapped[Optional[str]] = mapped_column(String(34), nullable=True)


class ContractRow(Base):
    __tablename__ = "contracts"

    contract_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(50), index=True)
    type: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    role_category: Mapped[str] = mapped_column(String(100))
    weekly_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2, asdecimal=True))
    fte_percent: Mapped[Decimal] = mapped_column(Numeric(5, 4, asdecimal=True))
    base_monthly_salary: Mapped[Decimal] = mapped_column(Numeric(15, 2, asdecimal=True))
    cct_reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: CCTReference
    company_id: Mapped[str] = mapped_column(String(50))
    pay_frequency: Mapped[str] = mapped_column(String(20))


class PayrollPeriodRow(Base):
    __tablename__ = "payroll_periods"

    period_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(50))
    pay_frequency: Mapped[str] = mapped_column(String(20))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    pay_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))


class TimeInputRow(Base):
    __tablename__ = "time_inputs"

    period_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    normal_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2, asdecimal=True))
    overtime_buckets: Mapped[str] = mapped_column(Text)   # JSON: OvertimeBuckets
    absences: Mapped[str] = mapped_column(Text)            # JSON: list[AbsenceEntry]
    meal_allowance_days: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str] = mapped_column(Text)


class PayslipRow(Base):
    __tablename__ = "payslips"

    period_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    employee_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    gross_earnings: Mapped[str] = mapped_column(Text)         # JSON: list[PayslipLine]
    deductions: Mapped[str] = mapped_column(Text)             # JSON: list[PayslipLine]
    employer_contributions: Mapped[str] = mapped_column(Text) # JSON: list[PayslipLine]
    net_pay: Mapped[Decimal] = mapped_column(Numeric(15, 2, asdecimal=True))
    audit: Mapped[str] = mapped_column(Text)                  # JSON: list[AuditTrailEntry]
