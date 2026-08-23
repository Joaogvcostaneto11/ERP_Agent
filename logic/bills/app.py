from __future__ import annotations
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from dotenv import load_dotenv

from db.connection import get_session as _read_session
from db.bills_connection import get_bills_write_session
from logic.chat.audit import AuditLog
from logic.bills.audit_writer import BillAuditWriter
from logic.bills.extract.ocr import pdf_to_text
from logic.bills.pending import PendingProposalStore
from logic.bills.rules.loader import RuleLoader
from logic.bills.service import BillService
from logic.bills.write_executor import BillWriteExecutor
from logic.common.password_gate import install_password_gate

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")

_RULES_DIR = _REPO_ROOT / "business_rules" / "bills"
_WRITE_LOG_PATH = Path(os.environ.get(
    "BILLS_WRITE_LOG_PATH", str(_REPO_ROOT / "logs" / "bills_writes.jsonl")))
_UI_DIR = _REPO_ROOT / "ui" / "bills"
_OPERATOR_COOKIE = "bills_operator"
# Writes land in whatever database BILLS_WRITE_DATABASE_URL points at (DevDB).
# Deliberately not a second, independent statement of the target: when the
# prefix named a database of its own, it drifted from the connection and the
# audit table was created somewhere the inserts never looked.
_TABLE_PREFIX = os.environ.get("BILLS_TABLE_PREFIX", "dbo.")

app = FastAPI(title="Bill Ingestion")

# This service writes to the ERP database, so it is gated whenever
# BILLS_APP_PASSWORD is set. Unset (local dev) installs no gate at all. The
# secret is deliberately separate from the chat service's APP_PASSWORD: leaking
# the read-only service must not hand over the one that writes.
install_password_gate(app, os.environ.get("BILLS_APP_PASSWORD"),
                      realm="Bill Ingestion")


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    """Render's health check. Declared here, above the StaticFiles mount at "/",
    because that mount answers anything not already routed — and exempt from the
    gate, or the check gets a 401 and the service never goes live."""
    return {"status": "ok"}

_service: BillService | None = None
_pending = PendingProposalStore()


def _read(sql: str, params: dict) -> list[dict]:
    with _read_session() as s:
        result = s.execute(text(sql), params or {})
        cols = list(result.keys())
        return [dict(zip(cols, row)) for row in result.fetchall()]


def _build_anthropic():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def get_service() -> BillService:
    global _service
    if _service is None:
        rule = RuleLoader(_RULES_DIR).rule()
        _service = BillService(
            anthropic_client=_build_anthropic(), ocr_fn=pdf_to_text, rule=rule,
            reader=_read, pending=_pending,
            executor=BillWriteExecutor(get_bills_write_session, table_prefix=_TABLE_PREFIX),
            audit=BillAuditWriter(AuditLog(_WRITE_LOG_PATH),
                                  session_factory=get_bills_write_session,
                                  table_prefix=_TABLE_PREFIX),
            model="claude-sonnet-4-6", table_prefix=_TABLE_PREFIX)
    return _service


def _operator(request: Request) -> str | None:
    return request.cookies.get(_OPERATOR_COOKIE)


@app.post("/bills/operator")
def set_operator(response: Response, body: dict) -> dict:
    name = (body or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    response.set_cookie(_OPERATOR_COOKIE, name, httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return {"operator": name}


@app.post("/bills/upload")
async def upload(request: Request, file: UploadFile = File(...)) -> Response:
    if not _operator(request):
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    data = await file.read()
    try:
        proposal = get_service().upload(data)
    except RuntimeError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    return JSONResponse(proposal.model_dump(mode="json"))


@app.post("/bills/stage/{proposal_id}")
async def stage(proposal_id: str, request: Request) -> Response:
    if not _operator(request):
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    edited = await request.json()
    try:
        return JSONResponse(get_service().stage(proposal_id, edited))
    except RuntimeError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)


@app.post("/bills/commit/{proposal_id}")
def commit(proposal_id: str, request: Request) -> Response:
    operator = _operator(request)
    if not operator:
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    try:
        return JSONResponse(get_service().commit(proposal_id, operator))
    except RuntimeError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)


@app.get("/favicon.ico", include_in_schema=False)
def _favicon() -> Response:
    return Response(status_code=204)


if _UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
