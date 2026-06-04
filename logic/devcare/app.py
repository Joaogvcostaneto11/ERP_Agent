from __future__ import annotations
import json as _json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from db.connection import get_session as _read_session
from db.devcare_connection import get_write_session
from logic.chat.audit import AuditLog
from logic.chat.events import ErrorCode, EventType
from logic.chat.history import HistoryStore
from logic.devcare.audit_writer import AuditWriter
from logic.devcare.pending import PendingChangeStore
from logic.devcare.rules.loader import RuleLoader
from logic.devcare.service import DevCareService
from logic.devcare.validator import ChangeValidator
from logic.devcare.write_executor import WriteExecutor

_REPO_ROOT = Path(__file__).resolve().parents[2]
from dotenv import load_dotenv
load_dotenv(_REPO_ROOT / ".env")

_RULES_DIR = _REPO_ROOT / "business_rules" / "devcare"
_HISTORY_PATH = Path(os.environ.get("DEVCARE_HISTORY_PATH",
                                    str(_REPO_ROOT / "logs" / "devcare_history.sqlite")))
_WRITE_LOG_PATH = Path(os.environ.get("DEVCARE_WRITE_LOG_PATH",
                                      str(_REPO_ROOT / "logs" / "devcare_writes.jsonl")))
_UI_DIR = _REPO_ROOT / "ui" / "devcare"
_SESSION_COOKIE = "devcare_session"
_OPERATOR_COOKIE = "devcare_operator"

app = FastAPI(title="DevCare Operations")

_service: DevCareService | None = None
_history: HistoryStore | None = None


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


def _get_history() -> HistoryStore:
    global _history
    if _history is None:
        _history = HistoryStore(_HISTORY_PATH)
    return _history


def get_service() -> DevCareService:
    global _service
    if _service is None:
        loader = RuleLoader(_RULES_DIR)
        _service = DevCareService(
            anthropic_client=_build_anthropic(),
            validator=ChangeValidator(loader, _read),
            loader=loader, reader=_read,
            pending=PendingChangeStore(),
            executor=WriteExecutor(get_write_session),
            audit=AuditWriter(AuditLog(_WRITE_LOG_PATH)),
            history=_get_history(), model="claude-sonnet-4-6",
        )
    return _service


def _session_id(request: Request, response: Response) -> str:
    sid = request.cookies.get(_SESSION_COOKIE)
    if not sid:
        sid = "s_" + secrets.token_hex(12)
        response.set_cookie(_SESSION_COOKIE, sid, httponly=True, samesite="lax",
                            max_age=60 * 60 * 24 * 7)
    return sid


def _operator(request: Request) -> str | None:
    return request.cookies.get(_OPERATOR_COOKIE)


@app.post("/devcare/operator")
def set_operator(request: Request, response: Response, body: dict) -> dict:
    name = (body or {}).get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    _session_id(request, response)
    response.set_cookie(_OPERATOR_COOKIE, name, httponly=True, samesite="lax",
                        max_age=60 * 60 * 24 * 7)
    return {"operator": name}


@app.post("/devcare/conversations")
def create_conversation(request: Request, response: Response) -> dict:
    sid = _session_id(request, response)
    return {"id": _get_history().create_conversation(sid)}


@app.get("/devcare/conversations")
def list_conversations(request: Request, response: Response) -> dict:
    sid = _session_id(request, response)
    rows = _get_history().list_conversations(sid)
    return {"conversations": [{"id": r.id, "title": r.title,
                               "updated_at": r.updated_at} for r in rows]}


def _format_sse(event: dict) -> bytes:
    name = event.get("type", "message")
    data = _json.dumps(event.get("payload", {}), default=str)
    return f"event: {name}\ndata: {data}\n\n".encode("utf-8")


@app.post("/devcare/operations")
async def post_operations(request: Request) -> Response:
    operator = _operator(request)
    if not operator:
        return JSONResponse({"detail": "operator not set"}, status_code=400)
    body = await request.json()
    conversation_id = body.get("conversation_id")
    message = body.get("message", "")
    if not conversation_id:
        return JSONResponse({"detail": "conversation_id required"}, status_code=400)
    sid = request.cookies.get(_SESSION_COOKIE) or ("s_" + secrets.token_hex(12))
    try:
        svc = get_service()
        async def gen():
            async for ev in svc.stream_turn(conversation_id, sid, operator, message):
                yield _format_sse(ev)
    except RuntimeError as e:
        async def gen():
            yield _format_sse({"type": EventType.ERROR.value,
                               "payload": {"code": ErrorCode.CONFIG.value,
                                           "message": str(e)}})
            yield _format_sse({"type": EventType.DONE.value, "payload": {}})
    resp = StreamingResponse(gen(), media_type="text/event-stream")
    resp.set_cookie(_SESSION_COOKIE, sid, httponly=True, samesite="lax",
                    max_age=60 * 60 * 24 * 7)
    return resp


@app.post("/devcare/commit/{change_id}")
async def commit(change_id: str, request: Request, response: Response) -> dict:
    operator = _operator(request)
    if not operator:
        raise HTTPException(status_code=400, detail="operator not set")
    sid = _session_id(request, response)
    body = await request.json()
    conversation_id = body.get("conversation_id")
    if not conversation_id:
        raise HTTPException(status_code=400, detail="conversation_id required")
    try:
        svc = get_service()
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
    return svc.commit_change(conversation_id, sid, operator, change_id)


if _UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
