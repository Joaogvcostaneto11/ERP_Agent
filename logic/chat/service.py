from __future__ import annotations
import asyncio
import json
import uuid
from collections import OrderedDict
from dataclasses import asdict
from typing import Any, AsyncIterator

from pydantic import ValidationError

from logic.chat.audit import AuditLog
from logic.chat.envelope import ClaudeEnvelope, RawReportBlock, ReportBlock
from logic.chat.events import ErrorCode, EventType, Phase
from logic.chat.pdf import PdfRenderer
from logic.chat.prompts import RUN_QUERY_TOOL
from logic.chat.schema_context import SchemaContext
from logic.chat.sql_executor import QueryError, QueryResult, SqlExecutor


MAX_QUERIES_PER_TURN = 10
MAX_SESSIONS = 100
MAX_HISTORY_MESSAGES = 40


class ChatService:
    def __init__(
        self,
        *,
        anthropic_client: Any,
        sql_executor: SqlExecutor,
        audit: AuditLog,
        schema_context: SchemaContext,
        pdf_renderer: PdfRenderer,
        model: str,
    ) -> None:
        self._anthropic = anthropic_client
        self._sql = sql_executor
        self._audit = audit
        self._schema = schema_context
        self._pdf = pdf_renderer
        self._model = model
        self._sessions: OrderedDict[str, list[dict]] = OrderedDict()

    def history(self, session_id: str) -> list[dict]:
        return self._sessions.get(session_id, [])

    def reset(self, session_id: str | None = None) -> None:
        if session_id is None:
            self._sessions.clear()
        else:
            self._sessions.pop(session_id, None)
        self._pdf.clear()

    def get_report_pdf(self, report_id: str) -> bytes:
        return self._pdf.get_pdf(report_id)

    def _get_or_create_history(self, session_id: str) -> list[dict]:
        if session_id in self._sessions:
            self._sessions.move_to_end(session_id)
            return self._sessions[session_id]
        while len(self._sessions) >= MAX_SESSIONS:
            self._sessions.popitem(last=False)
        history: list[dict] = []
        self._sessions[session_id] = history
        return history

    @staticmethod
    def _cap_history(history: list[dict]) -> None:
        if len(history) > MAX_HISTORY_MESSAGES:
            del history[: len(history) - MAX_HISTORY_MESSAGES]

    async def stream_turn(self, session_id: str, user_message: str) -> AsyncIterator[dict]:
        turn_id = "t_" + uuid.uuid4().hex[:12]
        history = self._get_or_create_history(session_id)
        history_snapshot = list(history)
        history.append({"role": "user", "content": user_message})
        queries_used = 0

        try:
            yield _event(EventType.STATUS, {"phase": Phase.THINKING.value})

            while True:
                response = await self._call_claude(history)

                tool_uses: list[Any] = []
                assistant_blocks: list[dict] = []
                for c in response.content:
                    ctype = getattr(c, "type", None)
                    if ctype == "text":
                        assistant_blocks.append({"type": "text", "text": c.text})
                    elif ctype == "tool_use":
                        tool_uses.append(c)
                        assistant_blocks.append({
                            "type": "tool_use",
                            "id": c.id,
                            "name": c.name,
                            "input": c.input,
                        })

                if not tool_uses:
                    raw = "".join(b["text"] for b in assistant_blocks if b["type"] == "text").strip()
                    history.append({"role": "assistant", "content": raw})
                    self._cap_history(history)
                    async for ev in self._emit_envelope(raw):
                        yield ev
                    yield _event(EventType.DONE, {})
                    return

                history.append({"role": "assistant", "content": assistant_blocks})

                if queries_used + len(tool_uses) > MAX_QUERIES_PER_TURN:
                    history[:] = history_snapshot
                    yield _event(EventType.ERROR, {
                        "code": ErrorCode.BUDGET_EXCEEDED.value,
                        "message": f"Query budget exceeded ({MAX_QUERIES_PER_TURN} per turn).",
                    })
                    return
                queries_used += len(tool_uses)

                for tu in tool_uses:
                    yield _event(EventType.STATUS, {
                        "phase": Phase.QUERYING.value,
                        "sql": tu.input.get("sql", ""),
                    })

                results = await asyncio.gather(*[
                    asyncio.to_thread(self._sql.run_query, tu.input.get("sql", ""))
                    for tu in tool_uses
                ])

                tool_results: list[dict] = []
                for tu, result in zip(tool_uses, results):
                    sql = tu.input.get("sql", "")
                    is_ok = isinstance(result, QueryResult)
                    self._audit.append({
                        "ts": AuditLog.now_iso(),
                        "turn_id": turn_id,
                        "session_id": session_id,
                        "user_msg": user_message,
                        "sql": sql,
                        "rows": result.row_count if is_ok else None,
                        "duration_ms": result.duration_ms if is_ok else None,
                        "status": "ok" if is_ok else "error",
                        "error_code": None if is_ok else result.code,
                    })
                    if is_ok:
                        tool_payload = {
                            "columns": result.columns,
                            "rows": result.rows,
                            "row_count": result.row_count,
                            "truncated": result.truncated,
                        }
                    else:
                        tool_payload = {"error": asdict(result)}
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(tool_payload, default=str),
                    })

                history.append({"role": "user", "content": tool_results})
        except Exception as e:
            history[:] = history_snapshot
            yield _event(EventType.ERROR, {
                "code": ErrorCode.INTERNAL.value,
                "message": str(e)[:500],
            })
            return

    async def _call_claude(self, history: list[dict]) -> Any:
        kwargs = dict(
            model=self._model,
            max_tokens=4096,
            system=self._schema.system_blocks(),
            tools=[RUN_QUERY_TOOL],
            messages=history,
        )
        stream_factory = getattr(self._anthropic.messages, "stream", None)
        if stream_factory is not None:
            ctx = stream_factory(**kwargs)
            if hasattr(ctx, "__aenter__"):
                async with ctx as stream:
                    return await stream.get_final_message()
        result = self._anthropic.messages.create(**kwargs)
        if asyncio.iscoroutine(result):
            return await result
        return result

    async def _emit_envelope(self, raw: str) -> AsyncIterator[dict]:
        try:
            data = json.loads(raw)
            env = ClaudeEnvelope.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            yield _event(EventType.ERROR, {
                "code": ErrorCode.ENVELOPE_PARSE.value,
                "message": f"could not parse assistant reply: {e}",
            })
            return

        for block in env.blocks:
            if isinstance(block, RawReportBlock):
                rid = self._pdf.register(block.html, block.title)
                emitted = ReportBlock(
                    id=rid, title=block.title, html=block.html,
                    pdf_url=f"/report/{rid}/pdf",
                )
                yield _event(EventType.BLOCK, emitted.model_dump())
            else:
                yield _event(EventType.BLOCK, block.model_dump())

        for c in env.citations:
            yield _event(EventType.CITATION, c.model_dump())


def _event(event_type: EventType, payload: dict) -> dict:
    return {"type": event_type.value, "payload": payload}
