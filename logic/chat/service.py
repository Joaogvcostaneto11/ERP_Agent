from __future__ import annotations
import json
import uuid
from dataclasses import asdict
from typing import Any, AsyncIterator

from pydantic import ValidationError

from logic.chat.audit import AuditLog
from logic.chat.envelope import ClaudeEnvelope, RawReportBlock, ReportBlock
from logic.chat.pdf import PdfRenderer
from logic.chat.prompts import RUN_QUERY_TOOL
from logic.chat.schema_context import SchemaContext
from logic.chat.sql_executor import QueryError, QueryResult, SqlExecutor


MAX_QUERIES_PER_TURN = 10


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
        self.messages: list[dict] = []

    def reset(self) -> None:
        self.messages = []
        self._pdf.clear()

    async def stream_turn(self, user_message: str) -> AsyncIterator[dict]:
        turn_id = "t_" + uuid.uuid4().hex[:12]
        history_before = list(self.messages)
        self.messages.append({"role": "user", "content": user_message})
        queries_used = 0

        try:
            yield {"type": "status", "payload": {"phase": "thinking"}}

            while True:
                response = self._anthropic.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    system=self._schema.system_blocks(),
                    tools=[RUN_QUERY_TOOL],
                    messages=self.messages,
                )

                tool_uses = [c for c in response.content if getattr(c, "type", None) == "tool_use"]

                if not tool_uses:
                    # final assistant message — parse envelope
                    text_parts = [c.text for c in response.content if getattr(c, "type", None) == "text"]
                    raw = "".join(text_parts).strip()
                    self.messages.append({"role": "assistant", "content": raw})
                    async for ev in self._emit_envelope(raw):
                        yield ev
                    yield {"type": "done", "payload": {}}
                    return

                # one or more tool calls — execute each, append to history, recurse
                assistant_blocks: list[dict] = []
                for tu in response.content:
                    if getattr(tu, "type", None) == "text":
                        assistant_blocks.append({"type": "text", "text": tu.text})
                    elif getattr(tu, "type", None) == "tool_use":
                        assistant_blocks.append({
                            "type": "tool_use",
                            "id": tu.id,
                            "name": tu.name,
                            "input": tu.input,
                        })
                self.messages.append({"role": "assistant", "content": assistant_blocks})

                tool_results: list[dict] = []
                for tu in tool_uses:
                    sql = tu.input.get("sql", "")
                    queries_used += 1
                    if queries_used > MAX_QUERIES_PER_TURN:
                        self.messages = history_before  # roll back this turn
                        yield {"type": "error", "payload": {
                            "code": "budget_exceeded",
                            "message": f"Query budget exceeded ({MAX_QUERIES_PER_TURN} per turn).",
                        }}
                        return

                    yield {"type": "status", "payload": {"phase": "querying", "sql": sql}}
                    result = self._sql.run_query(sql)
                    self._audit.append({
                        "ts": AuditLog.now_iso(),
                        "turn_id": turn_id,
                        "user_msg": user_message,
                        "sql": sql,
                        "rows": getattr(result, "row_count", None),
                        "duration_ms": getattr(result, "duration_ms", None),
                        "status": "ok" if isinstance(result, QueryResult) else "error",
                        "error_code": result.code if isinstance(result, QueryError) else None,
                    })
                    if isinstance(result, QueryResult):
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

                self.messages.append({"role": "user", "content": tool_results})
                # loop back for the next Claude call
        except Exception as e:
            self.messages = history_before
            yield {"type": "error", "payload": {"code": "internal", "message": str(e)[:500]}}
            return

    async def _emit_envelope(self, raw: str) -> AsyncIterator[dict]:
        try:
            data = json.loads(raw)
            env = ClaudeEnvelope.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as e:
            yield {"type": "error", "payload": {
                "code": "envelope_parse",
                "message": f"could not parse assistant reply: {e}",
            }}
            return

        for block in env.blocks:
            if isinstance(block, RawReportBlock):
                rid = self._pdf.register(block.html, block.title)
                emitted = ReportBlock(
                    id=rid, title=block.title, html=block.html,
                    pdf_url=f"/report/{rid}/pdf",
                )
                yield {"type": "block", "payload": emitted.model_dump()}
            else:
                yield {"type": "block", "payload": block.model_dump()}

        for c in env.citations:
            yield {"type": "citation", "payload": c.model_dump()}
