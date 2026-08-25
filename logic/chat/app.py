from __future__ import annotations
import asyncio
import hashlib
import html as _html
import json as _json
import os
import secrets
from collections.abc import AsyncIterator
from pathlib import Path

import nh3
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from db.connection import get_session as _session_factory
from logic.chat.audit import AuditLog
from logic.chat.events import ErrorCode, EventType
from logic.chat.history import HistoryStore
from logic.chat.knowledge_store import KnowledgeStore
from logic.chat.report_store import ReportNotFound, ReportStore
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService
from logic.chat.sql_executor import SqlExecutor
from logic.common.cookies import secure_cookie
from logic.common.password_gate import install_password_gate
from logic.common.security_headers import install_security_headers


_REPO_ROOT = Path(__file__).resolve().parents[2]
# Load .env from the repo root so `uvicorn logic.chat.app:app` works without a
# dotenv wrapper, regardless of the working directory it's launched from.
load_dotenv(_REPO_ROOT / ".env")
_SCHEMA_PATH: Path = _REPO_ROOT / "docs" / "db_schema.md"
_KNOWLEDGE_PATH: Path = _REPO_ROOT / "business_rules" / "query_knowledge.md"
_LOG_PATH: Path = _REPO_ROOT / "logs" / "queries.jsonl"
_HISTORY_PATH: Path = _REPO_ROOT / "logs" / "chat_history.sqlite"
_UI_DIR: Path = _REPO_ROOT / "ui" / "chat"
_SESSION_COOKIE = "chat_session"


def _build_anthropic_client():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set")
    import anthropic
    return anthropic.AsyncAnthropic(api_key=api_key, max_retries=5)


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
            knowledge_store=KnowledgeStore(_KNOWLEDGE_PATH),
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


# Shared-password gate for public deployment. Unset APP_PASSWORD (local dev)
# installs no gate at all.
install_password_gate(app, os.environ.get("APP_PASSWORD"), realm="ERP Chat")

# The chat UI is the only one that loads scripts from a CDN — marked, DOMPurify
# and Plotly, each pinned with an SRI hash in ui/chat/index.html. Naming the two
# hosts here means nothing else can inject a script tag that actually loads.
# 'unsafe-inline' for styles is unavoidable: Plotly writes <style> elements at
# runtime, and sanitized report HTML carries style attributes.
_CSP = ("default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net https://cdn.plot.ly; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'")
install_security_headers(app, csp=_CSP)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    return {"status": "ok"}


def _session_id(request: Request, response: Response) -> str:
    sid = request.cookies.get(_SESSION_COOKIE)
    if sid:
        return sid
    sid = "s_" + secrets.token_hex(12)
    response.set_cookie(
        _SESSION_COOKIE, sid,
        httponly=True, samesite="lax", secure=secure_cookie(request),
        max_age=60 * 60 * 24 * 7,
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


# Report bodies are written by the model, so this view has to treat them the
# same way ui/chat/renderers/report.js does — it runs them through DOMPurify
# before assigning innerHTML. Arriving server-side makes the HTML no more
# trustworthy: a report can quote whatever a query returned, and this page is
# served from the app's own origin.
#
# The allowlist is what a report is made of: headings, tables, lists and text.
# Nothing that loads or executes.
_REPORT_TAGS = {
    "p", "br", "hr", "div", "span", "blockquote", "pre", "code",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "small", "sub", "sup",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "colgroup", "col", "a",
}
_REPORT_ATTRS = {
    "*": {"class"},
    "a": {"href", "title"},
    "th": {"colspan", "rowspan", "scope"},
    "td": {"colspan", "rowspan"},
    "col": {"span"},
    "colgroup": {"span"},
}

# Belt and braces, the same way the bills rule path pairs _IDENT_RE with the
# schema probe: even if a tag ever slipped through the sanitizer, this page
# grants it nothing to run with. `style-src` covers /report.css plus the inline
# <style> block below; everything else is denied outright.
_REPORT_CSP = (
    "default-src 'none'; script-src 'none'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; base-uri 'none'; "
    "form-action 'none'; frame-ancestors 'none'"
)


@app.get("/report/{report_id}/view")
def get_report_view(report_id: str) -> Response:
    try:
        report = get_service().get_report(report_id)
    except ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found")
    html = _PRINT_VIEW_TEMPLATE.format(
        title=_html.escape(report.title),
        body=nh3.clean(report.html, tags=_REPORT_TAGS, attributes=_REPORT_ATTRS),
    )
    return Response(content=html, media_type="text/html",
                    headers={"Content-Security-Policy": _REPORT_CSP,
                             "X-Content-Type-Options": "nosniff"})


def _format_sse(event: dict) -> bytes:
    name = event.get("type", "message")
    data = _json.dumps(event.get("payload", {}), default=str)
    return f"event: {name}\ndata: {data}\n\n".encode("utf-8")


_KEEPALIVE_SECONDS = 15.0
_KEEPALIVE = b": keepalive\n\n"


async def _with_keepalive(events: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Emit an SSE comment whenever the turn goes quiet for _KEEPALIVE_SECONDS.

    A turn can block for a long time with nothing to send — a slow Claude call,
    or the SDK's exponential backoff after a 429/529. An idle-read timeout at a
    proxy (Render's included) then kills the connection and the browser sees a
    network error instead of the message the retry was about to produce.
    Comment chunks carry no data field, so ui/chat/sse.js drops them.
    """
    it = events.__aiter__()
    nxt: asyncio.Future | None = None
    try:
        while True:
            nxt = asyncio.ensure_future(it.__anext__())
            while True:
                done, _ = await asyncio.wait({nxt}, timeout=_KEEPALIVE_SECONDS)
                if done:
                    break
                yield _KEEPALIVE
            try:
                chunk = nxt.result()
            except StopAsyncIteration:
                return
            yield chunk
    finally:
        # On client disconnect GeneratorExit lands at a yield above, leaving the
        # in-flight __anext__ pending; cancelling it closes stream_turn so its
        # finally still writes the turn summary.
        if nxt is not None:
            nxt.cancel()


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
    resp = StreamingResponse(_with_keepalive(body_gen(sid)), media_type="text/event-stream")
    resp.set_cookie(
        _SESSION_COOKIE, sid,
        httponly=True, samesite="lax", secure=secure_cookie(request),
        max_age=60 * 60 * 24 * 7,
    )
    return resp


def _feedback_token() -> str | None:
    return os.environ.get("CHAT_FEEDBACK_TOKEN") or None


def _require_feedback(request: Request) -> None:
    token = _feedback_token()
    if not token:
        raise HTTPException(status_code=404, detail="feedback disabled")
    provided = request.headers.get("X-Feedback-Token", "")
    # Bytes, not str — see the note in logic/common/password_gate.py.
    if not secrets.compare_digest(provided.encode("utf-8"), token.encode("utf-8")):
        raise HTTPException(status_code=403, detail="invalid feedback token")


@app.get("/feedback/enabled")
def feedback_enabled() -> dict:
    return {"enabled": _feedback_token() is not None}


@app.post("/feedback/draft")
async def feedback_draft(request: Request) -> dict:
    _require_feedback(request)
    body = await request.json()
    entry = await get_service().draft_entry(
        body.get("question", ""), body.get("sql", ""), body.get("explanation", ""),
    )
    return {"entry": entry}


@app.post("/feedback/save")
async def feedback_save(request: Request) -> dict:
    _require_feedback(request)
    body = await request.json()
    ke_id = get_service().save_entry(
        entry=body.get("entry", ""),
        question=body.get("question", ""),
        explanation=body.get("explanation", ""),
        source_turn_id=body.get("source_turn_id", ""),
        conversation_id=body.get("conversation_id", ""),
    )
    return {"ke_id": ke_id}


def _asset_version() -> str:
    """Short token over the chat UI's JS/CSS; changes whenever any of them
    change, so the version-stamped URLs below always defeat a stale cache."""
    h = hashlib.md5()
    for p in sorted(_UI_DIR.rglob("*.js")) + sorted(_UI_DIR.rglob("*.css")):
        st = p.stat()
        h.update(f"{p.relative_to(_UI_DIR).as_posix()}:{st.st_mtime_ns}:{st.st_size}".encode())
    return h.hexdigest()[:8]


def _index() -> Response:
    """Serve index.html with version-stamped asset URLs so the browser always
    fetches the current app.js/chat.css after a change."""
    html = (_UI_DIR / "index.html").read_text(encoding="utf-8")
    v = _asset_version()
    html = html.replace('href="chat.css"', f'href="chat.css?v={v}"')
    html = html.replace('src="/app.js"', f'src="/app.js?v={v}"')
    return Response(content=html, media_type="text/html",
                    headers={"Cache-Control": "no-store"})


if _UI_DIR.exists():
    # Register the index routes BEFORE the catch-all mount so they win.
    app.add_api_route("/", _index, methods=["GET"], include_in_schema=False)
    app.add_api_route("/index.html", _index, methods=["GET"], include_in_schema=False)
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
