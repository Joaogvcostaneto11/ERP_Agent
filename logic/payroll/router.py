from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from db.database import get_db
from logic.payroll import conversation as conv
from logic.payroll import engine
from logic.payroll.models import (
    AdjustmentBody,
    ApproveBody,
    ConverseRequest,
    ConverseResponse,
    Employee,
    IntentRequest,
    PayrollRun,
    RunInitiateBody,
)

router = APIRouter(prefix="/payroll", tags=["payroll"])


# ── Employees ────────────────────────────────────────────────────────────────

@router.get("/employees", response_model=list[Employee])
def list_employees(db: Session = Depends(get_db)):
    return engine.list_employees(db)


@router.get("/employees/{employee_id}", response_model=Employee)
def get_employee(employee_id: str, db: Session = Depends(get_db)):
    try:
        return engine.get_employee(employee_id, db)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/employees", response_model=Employee, status_code=status.HTTP_201_CREATED)
def create_employee(employee: Employee, db: Session = Depends(get_db)):
    """Direct employee creation via API (bypasses the conversational flow)."""
    try:
        return engine.create_employee(employee, db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── Payroll runs ─────────────────────────────────────────────────────────────

@router.post("/runs", response_model=PayrollRun, status_code=status.HTTP_201_CREATED)
def initiate_run(body: RunInitiateBody, db: Session = Depends(get_db)):
    """Steps 1 & 2: collect inputs, validate rules, compute payslips. Returns run in 'review'."""
    try:
        return engine.initiate_run(body.run, body.employees, body.time_records, db)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/runs/{run_id}", response_model=PayrollRun)
def get_run(run_id: str, db: Session = Depends(get_db)):
    try:
        return engine.get_run(run_id, db)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/runs/{run_id}/approve", response_model=PayrollRun)
def approve_run(run_id: str, body: ApproveBody, db: Session = Depends(get_db)):
    """Step 3: finance_director approves the run. Moves status to 'committed'."""
    try:
        return engine.approve_run(run_id, body.approved_by, body.role, db)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/runs/{run_id}/commit", response_model=PayrollRun)
def commit_run(run_id: str, db: Session = Depends(get_db)):
    """Steps 4 + 5: persist audit records and mark run as 'disbursed'. Run becomes immutable."""
    try:
        return engine.commit_run(run_id, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/adjustments", status_code=status.HTTP_201_CREATED)
def create_adjustment(body: AdjustmentBody, db: Session = Depends(get_db)):
    """Create a delta adjustment against a closed run. Requires hr_manager role."""
    try:
        return engine.create_adjustment(body.adjustment, body.role, db)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── AI endpoints ─────────────────────────────────────────────────────────────

@router.post("/intent")
def process_intent(intent: IntentRequest):
    try:
        return engine.process_intent(intent)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/converse", response_model=ConverseResponse)
def converse(req: ConverseRequest):
    """
    Multi-turn conversational endpoint. Session state is maintained server-side.
    The AI collects missing fields through follow-up questions, then executes
    the action automatically when all data is gathered.
    """
    try:
        result = conv.converse(req.session_id, req.message, req.user_id, req.role)
        return ConverseResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
