from __future__ import annotations
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from fastapi import FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from logic.chat.audit import AuditLog
from logic.chat.pdf import PdfRenderer, ReportNotFound, WeasyPrintUnavailable
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService
from logic.chat.sql_executor import SqlExecutor


_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA_PATH: Path = _REPO_ROOT / "docs" / "db_schema.md"
_LOG_PATH: Path = _REPO_ROOT / "logs" / "queries.jsonl"
_UI_DIR: Path = _REPO_ROOT / "ui" / "chat"


@contextmanager
def _session_factory() -> Iterator[Session]:
    from db.connection import get_session
    with get_session() as s:
        yield s


def _build_anthropic_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


_service: ChatService | None = None


def get_service() -> ChatService:
    global _service
    if _service is None:
        _service = ChatService(
            anthropic_client=_build_anthropic_client(),
            sql_executor=SqlExecutor(_session_factory),
            audit=AuditLog(_LOG_PATH),
            schema_context=SchemaContext(_SCHEMA_PATH),
            pdf_renderer=PdfRenderer(),
            model="claude-sonnet-4-6",
        )
    return _service


def reset_service() -> None:
    global _service
    _service = None


app = FastAPI(title="ERP Chat")


@app.get("/config")
def get_config() -> dict:
    return {"voice_lang": os.environ.get("CHAT_VOICE_LANG", "pt-PT")}


@app.post("/chat/reset")
def post_chat_reset() -> dict:
    svc = get_service()
    svc.reset()
    return {"ok": True}


@app.get("/report/{report_id}/pdf")
def get_report_pdf(report_id: str) -> Response:
    svc = get_service()
    try:
        pdf = svc._pdf.get_pdf(report_id)
    except ReportNotFound:
        raise HTTPException(status_code=404, detail="report not found")
    except WeasyPrintUnavailable as e:
        return Response(
            content=str(e),
            status_code=501,
            media_type="text/plain",
        )
    return Response(content=pdf, media_type="application/pdf")


if _UI_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_UI_DIR), html=True), name="ui")
