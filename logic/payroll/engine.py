"""
Payroll run orchestration — implements the 5-step workflow from payroll.yaml §payroll_run.
All persistence goes through the db layer repositories; no in-memory state here.
"""
import uuid
from typing import Optional

from sqlalchemy.orm import Session

from logic.ai_engine import reason
from logic.payroll import calculator, validator
from logic.payroll.models import (
    AdjustmentRequest,
    Employee,
    IntentRequest,
    PayrollRun,
    PayrollRunRequest,
    Payslip,
    PayslipLine,
    RunStatus,
    TimeRecord,
)


# ── Employee operations ──────────────────────────────────────────────────────

def create_employee(employee: Employee, db: Session) -> Employee:
    from db.repositories.employees import EmployeeRepository
    from db.repositories.audit import AuditRepository

    repo = EmployeeRepository(db)
    audit = AuditRepository(db)

    if repo.exists(employee.id):
        raise ValueError(f"Employee '{employee.id}' already exists")
    errors = validator.validate_employee(employee)
    if errors:
        raise ValueError(errors[0])

    created = repo.create(employee)
    audit.log(
        user_id="system",
        action="create",
        entity_type="employee",
        entity_id=created.id,
        rule_applied="payroll.yaml §employee_types",
        rule_version="1.0.0",
        details={"name": created.name, "type": created.type},
    )
    db.commit()
    return created


def get_employee(employee_id: str, db: Session) -> Employee:
    from db.repositories.employees import EmployeeRepository
    return EmployeeRepository(db).get(employee_id)


def list_employees(db: Session) -> list[Employee]:
    from db.repositories.employees import EmployeeRepository
    return EmployeeRepository(db).list()


# ── Payroll run operations ───────────────────────────────────────────────────

def initiate_run(
    request: PayrollRunRequest,
    employees: list[Employee],
    time_records: list[TimeRecord],
    db: Session,
) -> PayrollRun:
    from db.repositories.payroll_runs import PayrollRunRepository
    from db.repositories.audit import AuditRepository

    # ── Step 1: collect & validate ───────────────────────────────────────────
    errors: list[str] = []
    errors += validator.validate_run_request(request, [])
    for emp in employees:
        errors += validator.validate_employee(emp)

    tr_map = {tr.employee_id: tr for tr in time_records}
    for emp in employees:
        tr = tr_map.get(emp.id)
        if tr:
            errors += validator.validate_time_record(tr, emp)

    _raise_if_errors(errors, "Payroll run blocked at collect step")

    # ── Step 2: calculate ────────────────────────────────────────────────────
    run_id = str(uuid.uuid4())
    payslips: list[Payslip] = []
    for emp in employees:
        gross = calculator.gross_pay(emp, tr_map.get(emp.id))
        ded_lines, total_deductions = calculator.deduction_lines(gross, emp.deduction_elections)
        net = round(gross - total_deductions, 2)
        errors += validator.validate_minimum_wage(net)
        payslips.append(Payslip(
            employee_id=emp.id,
            period_start=request.period_start,
            period_end=request.period_end,
            run_id=run_id,
            gross_pay=round(gross, 2),
            total_deductions=total_deductions,
            net_pay=net,
            lines=[
                PayslipLine(description="Gross Pay", amount=round(gross, 2), type="earning"),
                *ded_lines,
            ],
            rule_version="1.0.0",
        ))

    _raise_if_errors(errors, "Payroll run blocked at calculate step")

    run = PayrollRun(
        id=run_id,
        status=RunStatus.review,
        period_start=request.period_start,
        period_end=request.period_end,
        initiated_by=request.initiated_by,
        payslips=payslips,
    )

    # ── Persist (step 3 pending approval) ────────────────────────────────────
    repo = PayrollRunRepository(db)
    audit = AuditRepository(db)
    repo.create(run)
    audit.log(
        user_id=request.initiated_by,
        action="initiate",
        entity_type="payroll_run",
        entity_id=run_id,
        rule_applied="payroll.yaml §payroll_run",
        rule_version="1.0.0",
    )
    db.commit()
    return run


def approve_run(run_id: str, approved_by: str, approver_role: str, db: Session) -> PayrollRun:
    from db.repositories.payroll_runs import PayrollRunRepository
    from db.repositories.audit import AuditRepository

    errors = validator.validate_role_permission("approve_payroll_run", approver_role)
    if errors:
        raise PermissionError(errors[0])

    repo = PayrollRunRepository(db)
    run = repo.get(run_id)
    if run.status != RunStatus.review:
        raise ValueError(f"Run '{run_id}' is in status '{run.status}', expected 'review'")

    updated = repo.update_status(run_id, RunStatus.committed, approved_by=approved_by)
    AuditRepository(db).log(
        user_id=approved_by,
        action="approve",
        entity_type="payroll_run",
        entity_id=run_id,
        rule_applied="payroll.yaml §payroll_run.step3",
        rule_version="1.0.0",
    )
    db.commit()
    return updated


def commit_run(run_id: str, db: Session) -> PayrollRun:
    """
    Steps 4 + 5: mark as disbursed and write audit entries per payslip.
    A committed run is immutable — corrections require create_adjustment().
    """
    from db.repositories.payroll_runs import PayrollRunRepository
    from db.repositories.audit import AuditRepository

    repo = PayrollRunRepository(db)
    run = repo.get(run_id)
    if run.status != RunStatus.committed:
        raise ValueError(f"Run '{run_id}' is in status '{run.status}', expected 'committed'")

    audit = AuditRepository(db)
    for slip in run.payslips:
        audit.log(
            user_id="system",
            action="disburse",
            entity_type="payslip",
            entity_id=f"{run_id}/{slip.employee_id}",
            rule_applied="payroll.yaml §payroll_run.step4",
            rule_version=slip.rule_version,
            details={
                "employee_id": slip.employee_id,
                "gross": slip.gross_pay,
                "net": slip.net_pay,
            },
        )

    updated = repo.update_status(run_id, RunStatus.disbursed)
    db.commit()
    return updated


def get_run(run_id: str, db: Session) -> PayrollRun:
    from db.repositories.payroll_runs import PayrollRunRepository
    return PayrollRunRepository(db).get(run_id)


def create_adjustment(request: AdjustmentRequest, requester_role: str, db: Session) -> dict:
    from db.repositories.payroll_runs import PayrollRunRepository
    from db.repositories.audit import AuditRepository

    errors = validator.validate_role_permission("create_adjustment", requester_role)
    if errors:
        raise PermissionError(errors[0])

    original = PayrollRunRepository(db).get(request.original_run_id)
    if original.status not in (RunStatus.committed, RunStatus.disbursed):
        raise ValueError(
            "Adjustments may only target committed or disbursed runs "
            "(payroll.yaml §adjustments)"
        )

    adj_id = str(uuid.uuid4())
    AuditRepository(db).log(
        user_id=request.requested_by,
        action="adjustment_requested",
        entity_type="payroll_run",
        entity_id=request.original_run_id,
        rule_applied="payroll.yaml §adjustments",
        rule_version="1.0.0",
        details={"delta_gross": request.delta_gross, "reason": request.reason},
    )
    db.commit()

    return {
        "adjustment_id": adj_id,
        "original_run_id": request.original_run_id,
        "employee_id": request.employee_id,
        "delta_gross": request.delta_gross,
        "reason": request.reason,
        "status": "pending_approval",
        "rule_applied": "payroll.yaml §adjustments",
    }


# ── AI intent ────────────────────────────────────────────────────────────────

def process_intent(intent: IntentRequest) -> dict:
    return reason(
        domain="payroll",
        user_intent=intent.text,
        context={"user_id": intent.user_id, "role": intent.role, **intent.context},
    )


# ── helpers ──────────────────────────────────────────────────────────────────

def _raise_if_errors(errors: list[str], prefix: str) -> None:
    if errors:
        raise ValueError(f"{prefix}:\n" + "\n".join(f"  • {e}" for e in errors))
