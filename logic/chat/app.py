from __future__ import annotations
import html as _html
import json as _json
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from db.connection import get_session as _session_factory
from logic.chat.audit import AuditLog
from logic.chat.events import ErrorCode, EventType
from logic.chat.history import HistoryStore
from logic.chat.report_store import ReportNotFound, ReportStore
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService
from logic.chat.sql_executor import SqlExecutor


_REPO_ROOT = Path(__file__).resolve().parents[2]
# Load .env from the repo root so `uvicorn logic.chat.app:app` works without a
# dotenv wrapper, regardless of the working directory it's launched from.
load_dotenv(_REPO_ROOT / ".env")
_SCHEMA_PATH: Path = _REPO_ROOT / "docs" / "db_schema.md"
_LOG_PATH: Path = _REPO_ROOT / "logs" / "queries.jsonl"
_HISTORY_PATH: Path = _REPO_ROOT / "logs" / "chat_history.sqlite"
_UI_DIR: Path = _REPO_ROOT / "ui" / "chat"
_SESSION_COOKIE = "chat_session"


def _build_anthropic_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    return anthropic.AsyncAnthropic(api_key=api_key)


_service: ChatService | None = None
_history: HistoryStore | None = None


def _get_history() -> HistoryStore:
    global _history
    if _history is None:
        _history = HistoryStore(_HISTORY_PATH)
    return _history


def get_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService(
            anthropic_client=_build_anthropic_client(),
            sql_executor=SqlExecutor(_session_factory),
            audit=AuditLog(_LOG_PATH),
            schema_context=SchemaContext(_SCHEMA_PATH),
            report_store=ReportStore(),
            history=_get_history(),
            model="claude-sonnet-4-6",
        )
    return _service


def reset_service() -> None:
    global _service, _history
    _service = None
    if _history is not None:
        _history.close()
    _history = None


app = FastAPI(title="ERP Chat")


def _session_id(request: Request, response: Response) -> str:
    sid = request.cookies.get(_SESSION_COOKIE)
    if sid:
        return sid
    sid = "s_" + secrets.token_hex(12)
    response.set_cookie(
        _SESSION_COOKIE, sid,
        httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7,
    )
    return sid


@app.get("/conversations")
def list_conversations(request: Request, response: Response) -> dict:
    sid = _session_id(request, response)
    rows = _get_history().list_conversations(sid)
    return {"conversations": [
        {"id": r.id, "title": r.title, "updated_at": r.updated_at}
        for r in rows
    ]}


@app.post("/conversations")
def create_conversation(request: Request, response: Response) -> dict:
    sid = _session_id(request, response)
    cid = _get_history().create_conversation(sid)
    return {"id": cid}


@app.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, request: Request, response: Response) -> dict:
    sid = _session_id(request, response)
    detail = _get_history().get_conversation(conversation_id, sid)
    if detail is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    return {
        "id": detail.id,
        "title": detail.title,
        "created_at": detail.created_at,
        "updated_at": detail.updated_at,
        "turns": [
            {"user_message": t.user_message, "blocks": t.blocks,
             "citations": t.citations, "steps": t.steps, "ts": t.ts}
            for t in detail.turns
        ],
    }


@app.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, request: Request, response: Response) -> Response:
    sid = _session_id(request, response)
    ok = _get_history().delete_conversation(conversation_id, sid)
    if not ok:
        raise HTTPException(status_code=404, detail="conversation not found")
    return Response(status_code=204)


_PRINT_VIEW_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="/report.css">
<style>
  body {{ font-family: system-ui, sans-serif; padding: 24px; max-width: 900px; margin: 0 auto; }}
  .print-hint {{ background: #eef; border: 1px solid #99c; padding: 10px 14px; border-radius: 6px; margin-bottom: 24px; font-size: 14px; }}
  @media print {{ .print-hint {{ display: none; }} body {{ padding: 0; max-width: none; }} }}
</style>
</head><body>
<div class="print-hint">Press <kbd>Ctrl</kbd>+<kbd>P</kbd> (or <kbd>Cmd</kbd>+<kbd>P</kbd>) to save this report as a PDF.</div>
{body}
</body></html>
"""


@app.get("/report/{report_id}/view")
def get_report_view(report_id: str) -> Response:
    try:
        report = get_service().get_report(report_id)
    except ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found")
    html = _PRINT_VIEW_TEMPLATE.format(
        title=_html.escape(report.title),
        body=report.html,
    )
    return Response(content=html, media_type="text/html")


def _format_sse(event: dict) -> bytes:
    name = event.get("type", "message")
    data = _json.dumps(event.get("payload", {}), default=str)
    return f"event: {name}\ndata: {data}\n\n".encode("utf-8")


@app.post("/chat")
async def post_chat(request: Request) -> StreamingResponse:
    body = await request.json()
    user_message = body.get("message", "")
    conversation_id = body.get("conversation_id")
    if not conversation_id:
        return JSONResponse({"detail": "conversation_id is required"}, status_code=400)

    try:
        svc = get_service()
        async def body_gen(sid: str):
            async for ev in svc.stream_turn(conversation_id, sid, user_message):
                yield _format_sse(ev)
    except RuntimeError as e:
        err = _format_sse({
            "type": EventType.ERROR.value,
            "payload": {"code": ErrorCode.CONFIG.value, "message": str(e)},
        })
        done = _format_sse({"type": EventType.DONE.value, "payload": {}})
        async def body_gen(_sid: str):
            yield err
            yield done

    sid = request.cookies.get(_SESSION_COOKIE) or ("s_" + secrets.token_hex(12))
    resp = StreamingResponse(body_gen(sid), media_type="text/event-stream")
    resp.set_cookie(
        _SESSION_COOKIE, sid,
        httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7,
    )
    return resp


if _UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
