"""
Rule-based pre-flight validation against payroll.yaml.
Returns a list of error strings; an empty list means the input is valid.
Every error cites the rule section it enforces.
"""
from logic.payroll.models import Employee, EmployeeType, PayrollRunRequest, TimeRecord
from logic.rule_loader import load_rule


def _rules() -> dict:
    return load_rule("payroll")


def validate_employee(employee: Employee) -> list[str]:
    if employee.type == EmployeeType.contractor:
        return ["Contractors must not be processed through standard payroll (payroll.yaml §employee_types)"]
    return []


def validate_time_record(record: TimeRecord, employee: Employee) -> list[str]:
    errors: list[str] = []
    if employee.type == EmployeeType.hourly:
        if not record.approved:
            errors.append(
                f"Time record for employee '{record.employee_id}' must be approved "
                "before payroll can proceed (payroll.yaml §payroll_run.step1)"
            )
        if record.regular_hours < 0 or record.overtime_hours < 0:
            errors.append(f"Hours for employee '{record.employee_id}' must be non-negative")
    return errors


def validate_run_request(request: PayrollRunRequest, existing_run_ids: list[str]) -> list[str]:
    errors: list[str] = []
    if request.period_end <= request.period_start:
        errors.append("period_end must be after period_start")
    seen: set[str] = set()
    for eid in request.employee_ids:
        if eid in seen:
            errors.append(
                f"Employee '{eid}' appears more than once in the same run "
                "(payroll.yaml §payroll_run.step1)"
            )
        seen.add(eid)
    return errors


def validate_minimum_wage(net_pay: float, minimum_wage: float = 0.0) -> list[str]:
    if net_pay < minimum_wage:
        return [
            f"Net pay {net_pay:.2f} is below legal minimum wage {minimum_wage:.2f} "
            "(payroll.yaml §compensation.salary)"
        ]
    return []


def validate_role_permission(action: str, role: str) -> list[str]:
    """Check that `role` may perform `action` per payroll.yaml §permissions."""
    permissions: dict[str, list[str]] = _rules().get("permissions", {})
    allowed = permissions.get(action, [])
    if role not in allowed:
        return [
            f"Role '{role}' is not permitted to '{action}' "
            f"(payroll.yaml §permissions — allowed: {allowed})"
        ]
    return []
