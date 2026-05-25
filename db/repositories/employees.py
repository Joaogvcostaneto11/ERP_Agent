from sqlalchemy.orm import Session

from db.models import EmployeeDB
from logic.payroll.models import Employee


class EmployeeRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, employee: Employee) -> Employee:
        row = EmployeeDB(
            id=employee.id,
            name=employee.name,
            type=employee.type.value,
            pay_period=employee.pay_period.value,
            annual_salary=float(employee.annual_salary) if employee.annual_salary else None,
            hourly_rate=float(employee.hourly_rate) if employee.hourly_rate else None,
            deduction_elections=employee.deduction_elections,
        )
        self.db.add(row)
        self.db.flush()
        return self._to_model(row)

    def get(self, employee_id: str) -> Employee:
        row = self.db.get(EmployeeDB, employee_id)
        if row is None:
            raise KeyError(f"Employee '{employee_id}' not found")
        return self._to_model(row)

    def exists(self, employee_id: str) -> bool:
        return self.db.get(EmployeeDB, employee_id) is not None

    def list(self) -> list[Employee]:
        rows = self.db.query(EmployeeDB).order_by(EmployeeDB.created_at).all()
        return [self._to_model(r) for r in rows]

    def _to_model(self, row: EmployeeDB) -> Employee:
        return Employee(
            id=row.id,
            name=row.name,
            type=row.type,
            pay_period=row.pay_period,
            annual_salary=float(row.annual_salary) if row.annual_salary is not None else None,
            hourly_rate=float(row.hourly_rate) if row.hourly_rate is not None else None,
            deduction_elections=row.deduction_elections or [],
        )
