from __future__ import annotations
import asyncio
import json
import logging
import re
import uuid
from dataclasses import asdict
from typing import Any, AsyncIterator

from pydantic import ValidationError

from logic.chat.audit import AuditLog
from logic.chat.envelope import ClaudeEnvelope, RawReportBlock, ReportBlock
from logic.chat.events import ErrorCode, EventType, Phase
from logic.chat.history import HistoryStore
from logic.chat.prompts import RUN_QUERY_TOOL
from logic.chat.report_store import Report, ReportStore
from logic.chat.schema_context import SchemaContext
from logic.chat.sql_executor import QueryResult, SqlExecutor


MAX_QUERIES_PER_TURN = 10
TITLE_MODEL = "claude-haiku-4-5-20251001"

_log = logging.getLogger(__name__)


class ChatService:
    def __init__(
        self,
        *,
        anthropic_client: Any,
        sql_executor: SqlExecutor,
        audit: AuditLog,
        schema_context: SchemaContext,
        report_store: ReportStore,
        history: HistoryStore,
        model: str,
    ) -> None:
        self._anthropic = anthropic_client
        self._sql = sql_executor
        self._audit = audit
        self._schema = schema_context
        self._reports = report_store
        self._history = history
        self._model = model
        self._bg_tasks: set[asyncio.Task] = set()

    def get_report(self, report_id: str) -> Report:
        return self._reports.get(report_id)

    async def stream_turn(
        self, conversation_id: str, session_id: str, user_message: str
    ) -> AsyncIterator[dict]:
        if self._history.get_conversation(conversation_id, session_id) is None:
            yield _event(EventType.ERROR, {
                "code": ErrorCode.UNAUTHORIZED.value,
                "message": "conversation not found",
            })
            return

        turn_id = "t_" + uuid.uuid4().hex[:12]
        transcript = self._history.get_transcript(conversation_id, session_id)
        is_first_turn = not transcript
        transcript.append({"role": "user", "content": user_message})
        queries_used = 0
        emitted_blocks: list[dict] = []
        emitted_citations: list[dict] = []

        try:
            yield _event(EventType.STATUS, {"phase": Phase.THINKING.value})

            while True:
                response = await self._call_claude(transcript)

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
                    transcript.append({"role": "assistant", "content": raw})
                    async for ev in self._emit_envelope(raw, emitted_blocks, emitted_citations):
                        yield ev
                    self._history.append_turn(
                        conversation_id, session_id, user_message,
                        emitted_blocks, emitted_citations, transcript,
                    )
                    if is_first_turn:
                        t = asyncio.create_task(self._generate_title(
                            conversation_id, session_id, user_message, emitted_blocks
                        ))
                        self._bg_tasks.add(t)
                        t.add_done_callback(self._bg_tasks.discard)
                    yield _event(EventType.DONE, {})
                    return

                transcript.append({"role": "assistant", "content": assistant_blocks})

                if queries_used + len(tool_uses) > MAX_QUERIES_PER_TURN:
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
                        "conversation_id": conversation_id,
                        "session_id": session_id,
                        "user_msg": user_message,
                        "sql": sql,
                        "rows": result.row_count if is_ok else None,
                        "duration_ms": result.duration_ms if is_ok else None,
                        "status": "ok" if is_ok else "error",
                        "error_code": None if is_ok else result.code,
                    })
                    tool_payload = (
                        {"columns": result.columns, "rows": result.rows,
                         "row_count": result.row_count, "truncated": result.truncated}
                        if is_ok else
                        {"error": asdict(result)}
                    )
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(tool_payload, default=str),
                    })

                transcript.append({"role": "user", "content": tool_results})
        except Exception as e:
            yield _event(EventType.ERROR, {
                "code": ErrorCode.INTERNAL.value,
                "message": str(e)[:500],
            })
            return

    async def _call_claude(self, transcript: list[dict]) -> Any:
        kwargs = dict(
            model=self._model,
            max_tokens=4096,
            system=self._schema.system_blocks(),
            tools=[RUN_QUERY_TOOL],
            messages=transcript,
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

    async def _emit_envelope(
        self, raw: str, emitted_blocks: list[dict], emitted_citations: list[dict]
    ) -> AsyncIterator[dict]:
        try:
            data = _extract_envelope_object(raw)
            env = ClaudeEnvelope.model_validate(data)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            yield _event(EventType.ERROR, {
                "code": ErrorCode.ENVELOPE_PARSE.value,
                "message": f"could not parse assistant reply: {e}",
                "raw": raw[:500],
            })
            return

        for block in env.blocks:
            if isinstance(block, RawReportBlock):
                rid = self._reports.register(block.html, block.title)
                emitted = ReportBlock(
                    id=rid, title=block.title, html=block.html,
                    view_url=f"/report/{rid}/view",
                )
                payload = emitted.model_dump()
            else:
                payload = block.model_dump()
            emitted_blocks.append(payload)
            yield _event(EventType.BLOCK, payload)

        for c in env.citations:
            payload = c.model_dump()
            emitted_citations.append(payload)
            yield _event(EventType.CITATION, payload)

    async def _generate_title(
        self, conversation_id: str, session_id: str,
        user_message: str, blocks: list[dict],
    ) -> None:
        preview = _assistant_preview(blocks)
        prompt = (
            "Summarise this exchange as a 5-7 word title. No quotes, no trailing punctuation.\n\n"
            f"USER: {user_message[:500]}\n"
            f"ASSISTANT: {preview[:500]}"
        )
        try:
            result = self._anthropic.messages.create(
                model=TITLE_MODEL,
                max_tokens=30,
                messages=[{"role": "user", "content": prompt}],
            )
            if asyncio.iscoroutine(result):
                result = await result
            title = "".join(
                getattr(c, "text", "") for c in result.content
                if getattr(c, "type", None) == "text"
            ).strip()[:80]
            if title:
                self._history.update_title(conversation_id, session_id, title)
        except Exception:
            _log.exception("title generation failed")


def _assistant_preview(blocks: list[dict]) -> str:
    for b in blocks:
        if b.get("kind") == "text":
            return b.get("markdown", "")
    if not blocks:
        return ""
    b = blocks[0]
    kind = b.get("kind")
    if kind == "value":
        return f"Value: {b.get('label', '')} = {b.get('value', '')}"
    if kind == "table":
        cols = len(b.get("columns", []))
        rows = len(b.get("rows", []))
        return f"Table with {rows} rows and {cols} columns"
    if kind == "chart":
        return f"Chart: {b.get('title', '')}"
    if kind == "report":
        return f"Report: {b.get('title', '')}"
    return f"{kind} block"


def _event(event_type: EventType, payload: dict) -> dict:
    return {"type": event_type.value, "payload": payload}


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def _extract_envelope_object(raw: str) -> dict:
    """Locate the envelope JSON object inside prose / markdown fences."""
    decoder = json.JSONDecoder()
    for candidate in _envelope_candidates(raw):
        try:
            obj, _ = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and "blocks" in obj:
            return obj
    raise ValueError("no JSON object with a 'blocks' key found in reply")


def _envelope_candidates(raw: str):
    yield raw.strip()
    for m in _FENCE_RE.finditer(raw):
        yield m.group(1)
    for i, ch in enumerate(raw):
        if ch == "{":
            yield raw[i:]
