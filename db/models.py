from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, JSON, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class EmployeeDB(Base):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    pay_period: Mapped[str] = mapped_column(String, nullable=False)
    annual_salary: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    hourly_rate: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    deduction_elections: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    payslips: Mapped[list[PayslipDB]] = relationship(back_populates="employee")


class PayrollRunDB(Base):
    __tablename__ = "payroll_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    initiated_by: Mapped[str] = mapped_column(String, nullable=False)
    approved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rule_version: Mapped[str] = mapped_column(String, nullable=False, default="1.0.0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    payslips: Mapped[list[PayslipDB]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class PayslipDB(Base):
    __tablename__ = "payslips"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payroll_runs.id"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        String, ForeignKey("employees.id"), nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    gross_pay: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    total_deductions: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    net_pay: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    rule_version: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    run: Mapped[PayrollRunDB] = relationship(back_populates="payslips")
    employee: Mapped[EmployeeDB] = relationship(back_populates="payslips")
    lines: Mapped[list[PayslipLineDB]] = relationship(
        back_populates="payslip", cascade="all, delete-orphan"
    )


class PayslipLineDB(Base):
    __tablename__ = "payslip_lines"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    payslip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payslips.id"), nullable=False
    )
    description: Mapped[str] = mapped_column(String, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)

    payslip: Mapped[PayslipDB] = relationship(back_populates="lines")


class AuditLogDB(Base):
    """Immutable audit trail — no update or delete methods are exposed."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    entity_id: Mapped[str] = mapped_column(String, nullable=False)
    rule_applied: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rule_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
