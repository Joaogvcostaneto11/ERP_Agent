from __future__ import annotations
import html as _html
import json as _json
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from db.connection import get_session as _session_factory
from logic.chat.audit import AuditLog
from logic.chat.events import ErrorCode, EventType
from logic.chat.report_store import ReportNotFound, ReportStore
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService
from logic.chat.sql_executor import SqlExecutor


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH: Path = _REPO_ROOT / "docs" / "db_schema.md"
_LOG_PATH: Path = _REPO_ROOT / "logs" / "queries.jsonl"
_UI_DIR: Path = _REPO_ROOT / "ui" / "chat"
_SESSION_COOKIE = "chat_session"


def _build_anthropic_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    return anthropic.AsyncAnthropic(api_key=api_key)


_service: ChatService | None = None


def get_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService(
            anthropic_client=_build_anthropic_client(),
            sql_executor=SqlExecutor(_session_factory),
            audit=AuditLog(_LOG_PATH),
            schema_context=SchemaContext(_SCHEMA_PATH),
            report_store=ReportStore(),
            model="claude-sonnet-4-6",
        )
    return _service


def reset_service() -> None:
    global _service
    _service = None


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


@app.get("/config")
def get_config() -> dict:
    return {"voice_lang": os.environ.get("CHAT_VOICE_LANG", "pt-PT")}


@app.post("/chat/reset")
def post_chat_reset(request: Request, response: Response) -> dict:
    sid = _session_id(request, response)
    get_service().reset(sid)
    return {"ok": True}


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

    try:
        svc = get_service()
        async def body_gen(sid: str):
            async for ev in svc.stream_turn(sid, user_message):
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
    if _SESSION_COOKIE not in request.cookies:
        resp.set_cookie(
            _SESSION_COOKIE, sid,
            httponly=True, samesite="lax", max_age=60 * 60 * 24 * 7,
        )
    return resp


if _UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
