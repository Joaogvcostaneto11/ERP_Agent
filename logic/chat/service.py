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


TITLE_MODEL = "claude-haiku-4-5-20251001"
STEP_ROWS_PREVIEW = 5  # rows captured per query for the Details view

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
        emitted_blocks: list[dict] = []
        emitted_citations: list[dict] = []
        emitted_steps: list[dict] = []
        status = "ok"

        try:
            yield _event(EventType.STATUS, {"phase": Phase.THINKING.value})

            while True:
                response = await self._call_claude(transcript)

                usage_step = _usage_step(response, self._model)
                if usage_step is not None:
                    emitted_steps.append(usage_step)
                    yield _event(EventType.STEP, usage_step)

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
                        emitted_blocks, emitted_citations, emitted_steps, transcript,
                    )
                    if is_first_turn:
                        t = asyncio.create_task(self._generate_title(
                            conversation_id, session_id, user_message, emitted_blocks
                        ))
                        self._bg_tasks.add(t)
                        t.add_done_callback(self._bg_tasks.discard)
                    yield _event(EventType.DONE, {})
                    return

                # Intermediate reasoning text (Claude's prose before a tool round)
                reasoning = "".join(b["text"] for b in assistant_blocks if b["type"] == "text").strip()
                if reasoning:
                    step = {"type": "reasoning", "text": reasoning}
                    emitted_steps.append(step)
                    yield _event(EventType.STEP, step)

                transcript.append({"role": "assistant", "content": assistant_blocks})

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
                    if is_ok:
                        tool_payload = {
                            "columns": result.columns, "rows": result.rows,
                            "row_count": result.row_count, "truncated": result.truncated,
                        }
                        step = {
                            "type": "query",
                            "sql": sql,
                            "row_count": result.row_count,
                            "duration_ms": result.duration_ms,
                            "truncated": result.truncated,
                            "columns": result.columns,
                            "rows_preview": result.rows[:STEP_ROWS_PREVIEW],
                            "error_code": None,
                            "error_message": None,
                        }
                    else:
                        tool_payload = {"error": asdict(result)}
                        step = {
                            "type": "query",
                            "sql": sql,
                            "row_count": None,
                            "duration_ms": None,
                            "truncated": None,
                            "columns": None,
                            "rows_preview": None,
                            "error_code": result.code,
                            "error_message": result.message,
                        }
                    emitted_steps.append(step)
                    yield _event(EventType.STEP, step)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": json.dumps(tool_payload, default=str),
                    })

                transcript.append({"role": "user", "content": tool_results})
        except Exception as e:
            status = "error"
            yield _event(EventType.ERROR, {
                "code": ErrorCode.INTERNAL.value,
                "message": str(e)[:500],
            })
            return
        finally:
            self._write_turn_summary(
                turn_id, conversation_id, session_id, user_message,
                emitted_steps, status,
            )

    def _write_turn_summary(
        self, turn_id: str, conversation_id: str, session_id: str,
        user_message: str, steps: list[dict], status: str,
    ) -> None:
        """One line per turn in queries.jsonl with kind='turn_summary',
        aggregating all Claude calls (token counts + USD cost) and SQL
        query count. Distinguishable from per-query rows via the kind field.
        """
        usages = [s for s in steps if s.get("type") == "usage"]
        self._audit.append({
            "ts": AuditLog.now_iso(),
            "kind": "turn_summary",
            "turn_id": turn_id,
            "conversation_id": conversation_id,
            "session_id": session_id,
            "user_msg": user_message,
            "status": status,
            "claude_calls": len(usages),
            "sql_queries": sum(1 for s in steps if s.get("type") == "query"),
            "total_input_tokens": sum(u.get("input_tokens", 0) for u in usages),
            "total_output_tokens": sum(u.get("output_tokens", 0) for u in usages),
            "total_cache_read_input_tokens": sum(u.get("cache_read_input_tokens", 0) for u in usages),
            "total_cache_creation_input_tokens": sum(u.get("cache_creation_input_tokens", 0) for u in usages),
            "total_cost_usd": round(sum((u.get("cost_usd") or 0) for u in usages), 6),
        })

    async def _call_claude(self, transcript: list[dict]) -> Any:
        kwargs = dict(
            model=self._model,
            max_tokens=4096,
            system=self._schema.system_blocks(),
            tools=[RUN_QUERY_TOOL],
            messages=_compress_past_turns_for_claude(transcript),
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


def _usage_step(response: Any, model: str) -> dict | None:
    """Extract token usage from an Anthropic response into a usage step,
    including an estimated USD cost for the given model. Returns None if the
    response has no usage attribute (e.g. test fakes).
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    def _i(name: str) -> int:
        v = getattr(usage, name, 0)
        return int(v) if v is not None else 0
    step = {
        "type": "usage",
        "input_tokens": _i("input_tokens"),
        "output_tokens": _i("output_tokens"),
        "cache_read_input_tokens": _i("cache_read_input_tokens"),
        "cache_creation_input_tokens": _i("cache_creation_input_tokens"),
    }
    cost = _estimate_cost_usd(model, step)
    if cost is not None:
        step["cost_usd"] = cost
    return step


# Anthropic API list price in USD per 1M tokens, as of 2026-05.
# Cache writes are 1.25x base input; cache reads are 0.10x base input.
# Update when pricing changes; persisted historical costs keep the original
# at-the-time value because the cost is embedded in steps_json.
_PRICING_USD_PER_MTOK = {
    "claude-opus-4-8":           {"in": 15.00, "out": 75.00, "cache_read": 1.50, "cache_write": 18.75},
    "claude-opus-4-7":           {"in": 15.00, "out": 75.00, "cache_read": 1.50, "cache_write": 18.75},
    "claude-sonnet-4-6":         {"in":  3.00, "out": 15.00, "cache_read": 0.30, "cache_write":  3.75},
    "claude-haiku-4-5-20251001": {"in":  1.00, "out":  5.00, "cache_read": 0.10, "cache_write":  1.25},
}


def _estimate_cost_usd(model: str, usage: dict) -> float | None:
    p = _PRICING_USD_PER_MTOK.get(model)
    if p is None:
        return None
    return round(
        (
            usage["input_tokens"] * p["in"]
            + usage["output_tokens"] * p["out"]
            + usage["cache_read_input_tokens"] * p["cache_read"]
            + usage["cache_creation_input_tokens"] * p["cache_write"]
        )
        / 1_000_000,
        6,
    )


def _compress_past_turns_for_claude(transcript: list[dict]) -> list[dict]:
    """Drop intermediate tool_use/tool_result pairs from past turns to save
    input tokens. The most recent turn (from the last user-string message
    onward) is preserved verbatim so the in-flight reasoning chain stays
    intact for Claude. Each past turn collapses to [user question, final
    assistant answer]; everything between is dropped.
    """
    if not transcript:
        return transcript
    last_user_idx = None
    for i in range(len(transcript) - 1, -1, -1):
        m = transcript[i]
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            last_user_idx = i
            break
    if last_user_idx is None:
        return list(transcript)
    return _compress_past(transcript[:last_user_idx]) + list(transcript[last_user_idx:])


def _compress_past(past: list[dict]) -> list[dict]:
    """For each past turn (delimited by user-string messages), keep only the
    user question and the final assistant-string answer. Drops the tool_use
    / tool_result chain between them. The retained assistant answer also has
    its table/chart/report blocks replaced with one-line summaries to keep
    row data out of input tokens.
    """
    out: list[dict] = []
    i = 0
    n = len(past)
    while i < n:
        m = past[i]
        if m.get("role") == "user" and isinstance(m.get("content"), str):
            out.append(m)
            final_assistant: dict | None = None
            j = i + 1
            while j < n:
                mj = past[j]
                if mj.get("role") == "user" and isinstance(mj.get("content"), str):
                    break
                if mj.get("role") == "assistant" and isinstance(mj.get("content"), str):
                    final_assistant = mj
                j += 1
            if final_assistant is not None:
                stripped = dict(final_assistant)
                stripped["content"] = _strip_heavy_blocks_from_envelope(final_assistant["content"])
                out.append(stripped)
            i = j
        else:
            # Stray message at the head — keep so Anthropic doesn't reject
            out.append(m)
            i += 1
    return out


_HEAVY_BLOCK_KINDS = {"table", "chart", "report"}


def _strip_heavy_blocks_from_envelope(content: str) -> str:
    """If ``content`` parses as a Claude envelope, replace its table / chart /
    report blocks with one-line text summaries (preserving column names for
    tables, titles for charts and reports) and re-serialise. Other blocks
    (text, value) and citations are kept verbatim. Non-envelope strings are
    returned unchanged.
    """
    try:
        env = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return content
    if not (isinstance(env, dict) and isinstance(env.get("blocks"), list)):
        return content
    new_blocks: list[dict] = []
    for b in env["blocks"]:
        if not (isinstance(b, dict) and b.get("kind") in _HEAVY_BLOCK_KINDS):
            new_blocks.append(b)
            continue
        new_blocks.append({"kind": "text", "markdown": _summarise_heavy_block(b)})
    env["blocks"] = new_blocks
    return json.dumps(env, default=str)


def _summarise_heavy_block(block: dict) -> str:
    kind = block.get("kind")
    if kind == "table":
        cols = block.get("columns") or []
        rows = block.get("rows") or []
        caption = block.get("caption")
        col_list = ", ".join(str(c) for c in cols) if cols else "(no columns)"
        suffix = f" — caption: {caption!r}" if caption else ""
        return f"[earlier table omitted: {len(rows)} rows × {len(cols)} cols. Columns: {col_list}{suffix}]"
    if kind == "chart":
        title = block.get("title") or "untitled"
        return f"[earlier chart omitted: {title!r}]"
    if kind == "report":
        title = block.get("title") or "untitled"
        return f"[earlier report omitted: {title!r}]"
    return f"[earlier {kind} block omitted]"


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
