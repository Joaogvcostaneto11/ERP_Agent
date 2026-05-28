from __future__ import annotations
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from logic.chat.audit import AuditLog
from logic.chat.pdf import PdfRenderer
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService
from logic.chat.sql_executor import SqlExecutor


# --- fakes ---

class _ContentText:
    type = "text"
    def __init__(self, text: str) -> None:
        self.text = text


class _ContentToolUse:
    type = "tool_use"
    def __init__(self, tool_id: str, name: str, sql: str) -> None:
        self.id = tool_id
        self.name = name
        self.input = {"sql": sql}


class _Response:
    def __init__(self, content: list, stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason


class FakeAnthropicClient:
    def __init__(self, scripted: list[_Response]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw) -> _Response:
        self.calls.append(kw)
        if not self._scripted:
            raise AssertionError("FakeAnthropicClient ran out of scripted responses")
        return self._scripted.pop(0)


class _FakeSession:
    def execute(self, stmt) -> Any:
        s = str(stmt)
        class _R:
            def keys(self_inner): return ["n"]
            def fetchall(self_inner): return [[42]]
        if "SET LOCK_TIMEOUT" in s:
            class _Empty:
                def keys(self_inner): return []
                def fetchall(self_inner): return []
            return _Empty()
        return _R()


@contextmanager
def _factory() -> Iterator[_FakeSession]:
    yield _FakeSession()


@pytest.fixture
def schema_ctx(tmp_path: Path) -> SchemaContext:
    p = tmp_path / "schema.md"
    p.write_text("Tables: foo.", encoding="utf-8")
    return SchemaContext(schema_path=p)


@pytest.fixture
def audit(tmp_path: Path) -> AuditLog:
    return AuditLog(tmp_path / "queries.jsonl")


@pytest.fixture
def pdf_renderer() -> PdfRenderer:
    return PdfRenderer()


@pytest.fixture
def sql_executor() -> SqlExecutor:
    return SqlExecutor(_factory)


# --- tests ---

@pytest.mark.asyncio
async def test_immediate_text_reply_no_tool_use(schema_ctx, audit, pdf_renderer, sql_executor):
    envelope_json = json.dumps({"blocks": [{"kind": "text", "markdown": "hi"}], "citations": []})
    client = FakeAnthropicClient([_Response([_ContentText(envelope_json)], stop_reason="end_turn")])
    svc = ChatService(
        anthropic_client=client,
        sql_executor=sql_executor,
        audit=audit,
        schema_context=schema_ctx,
        pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    events = [e async for e in svc.stream_turn("hello")]
    types = [e["type"] for e in events]
    assert types[0] == "status"
    assert "block" in types
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_tool_use_round_trip(schema_ctx, audit, pdf_renderer, sql_executor):
    final = json.dumps({"blocks": [{"kind": "value", "label": "n", "value": 42}], "citations": []})
    client = FakeAnthropicClient([
        _Response([_ContentToolUse("t1", "run_query", "SELECT 42 AS n")], stop_reason="tool_use"),
        _Response([_ContentText(final)], stop_reason="end_turn"),
    ])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor,
        audit=audit, schema_context=schema_ctx, pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    events = [e async for e in svc.stream_turn("count")]
    # we should see a 'querying' status, then a value block
    statuses = [e for e in events if e["type"] == "status"]
    blocks = [e for e in events if e["type"] == "block"]
    assert any(s["payload"].get("phase") == "querying" for s in statuses)
    assert len(blocks) == 1 and blocks[0]["payload"]["kind"] == "value"
    # claude was called twice
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_query_budget_exceeded(schema_ctx, audit, pdf_renderer, sql_executor):
    # script 11 tool_use responses → loop should abort after the 10th
    tool_use = lambda i: _Response(
        [_ContentToolUse(f"t{i}", "run_query", f"SELECT {i}")],
        stop_reason="tool_use",
    )
    client = FakeAnthropicClient([tool_use(i) for i in range(11)])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor,
        audit=audit, schema_context=schema_ctx, pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    events = [e async for e in svc.stream_turn("loop")]
    errors = [e for e in events if e["type"] == "error"]
    assert errors and "budget" in errors[0]["payload"]["message"].lower()


@pytest.mark.asyncio
async def test_malformed_envelope_emits_error(schema_ctx, audit, pdf_renderer, sql_executor):
    client = FakeAnthropicClient([_Response([_ContentText("not json at all")], stop_reason="end_turn")])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor,
        audit=audit, schema_context=schema_ctx, pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    events = [e async for e in svc.stream_turn("x")]
    assert any(e["type"] == "error" for e in events)


@pytest.mark.asyncio
async def test_report_block_gets_id_and_pdf_url(schema_ctx, audit, pdf_renderer, sql_executor):
    env = json.dumps({
        "blocks": [{"kind": "report", "title": "T", "html": "<p>x</p>"}],
        "citations": [],
    })
    client = FakeAnthropicClient([_Response([_ContentText(env)], stop_reason="end_turn")])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor,
        audit=audit, schema_context=schema_ctx, pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    events = [e async for e in svc.stream_turn("report me")]
    report_blocks = [e for e in events if e["type"] == "block" and e["payload"]["kind"] == "report"]
    assert len(report_blocks) == 1
    p = report_blocks[0]["payload"]
    assert p["id"].startswith("r_")
    assert p["pdf_url"] == f"/report/{p['id']}/pdf"


def test_reset_clears_history(schema_ctx, audit, pdf_renderer, sql_executor):
    client = FakeAnthropicClient([])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor,
        audit=audit, schema_context=schema_ctx, pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )
    svc.messages.append({"role": "user", "content": "old"})
    svc.reset()
    assert svc.messages == []
