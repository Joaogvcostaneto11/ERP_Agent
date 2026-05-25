import uuid

from sqlalchemy.orm import Session, joinedload

from db.models import PayrollRunDB, PayslipDB, PayslipLineDB
from logic.payroll.models import Payslip, PayslipLine, PayrollRun, RunStatus


class PayrollRunRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, run: PayrollRun) -> PayrollRun:
        run_row = PayrollRunDB(
            id=run.id,
            status=run.status.value,
            period_start=run.period_start,
            period_end=run.period_end,
            initiated_by=run.initiated_by,
            approved_by=run.approved_by,
            rule_version=run.rule_version,
        )
        self.db.add(run_row)

        for slip in run.payslips:
            slip_row = PayslipDB(
                id=str(uuid.uuid4()),
                run_id=run.id,
                employee_id=slip.employee_id,
                period_start=slip.period_start,
                period_end=slip.period_end,
                gross_pay=slip.gross_pay,
                total_deductions=slip.total_deductions,
                net_pay=slip.net_pay,
                rule_version=slip.rule_version,
            )
            self.db.add(slip_row)
            for line in slip.lines:
                self.db.add(PayslipLineDB(
                    id=str(uuid.uuid4()),
                    payslip_id=slip_row.id,
                    description=line.description,
                    amount=line.amount,
                    type=line.type,
                ))

        self.db.flush()
        return run

    def get(self, run_id: str) -> PayrollRun:
        row = (
            self.db.query(PayrollRunDB)
            .options(
                joinedload(PayrollRunDB.payslips).joinedload(PayslipDB.lines)
            )
            .filter(PayrollRunDB.id == run_id)
            .first()
        )
        if row is None:
            raise KeyError(f"Payroll run '{run_id}' not found")
        return self._to_model(row)

    def update_status(self, run_id: str, status: RunStatus, approved_by: str = None) -> PayrollRun:
        row = self.db.get(PayrollRunDB, run_id)
        if row is None:
            raise KeyError(f"Payroll run '{run_id}' not found")
        row.status = status.value
        if approved_by is not None:
            row.approved_by = approved_by
        self.db.flush()
        return self.get(run_id)

    def _to_model(self, row: PayrollRunDB) -> PayrollRun:
        payslips = []
        for s in row.payslips:
            lines = [
                PayslipLine(description=l.description, amount=float(l.amount), type=l.type)
                for l in s.lines
            ]
            payslips.append(Payslip(
                employee_id=s.employee_id,
                period_start=s.period_start,
                period_end=s.period_end,
                run_id=row.id,
                gross_pay=float(s.gross_pay),
                total_deductions=float(s.total_deductions),
                net_pay=float(s.net_pay),
                lines=lines,
                rule_version=s.rule_version,
            ))
        return PayrollRun(
            id=row.id,
            status=RunStatus(row.status),
            period_start=row.period_start,
            period_end=row.period_end,
            initiated_by=row.initiated_by,
            approved_by=row.approved_by,
            payslips=payslips,
            rule_version=row.rule_version,
        )
