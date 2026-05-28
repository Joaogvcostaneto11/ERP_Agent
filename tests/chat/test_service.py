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


SESSION = "s_test"


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


def _make_service(client, schema_ctx, audit, pdf_renderer, sql_executor) -> ChatService:
    return ChatService(
        anthropic_client=client,
        sql_executor=sql_executor,
        audit=audit,
        schema_context=schema_ctx,
        pdf_renderer=pdf_renderer,
        model="claude-sonnet-4-6",
    )


# --- tests ---

@pytest.mark.asyncio
async def test_immediate_text_reply_no_tool_use(schema_ctx, audit, pdf_renderer, sql_executor):
    envelope_json = json.dumps({"blocks": [{"kind": "text", "markdown": "hi"}], "citations": []})
    client = FakeAnthropicClient([_Response([_ContentText(envelope_json)], stop_reason="end_turn")])
    svc = _make_service(client, schema_ctx, audit, pdf_renderer, sql_executor)
    events = [e async for e in svc.stream_turn(SESSION, "hello")]
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
    svc = _make_service(client, schema_ctx, audit, pdf_renderer, sql_executor)
    events = [e async for e in svc.stream_turn(SESSION, "count")]
    statuses = [e for e in events if e["type"] == "status"]
    blocks = [e for e in events if e["type"] == "block"]
    assert any(s["payload"].get("phase") == "querying" for s in statuses)
    assert len(blocks) == 1 and blocks[0]["payload"]["kind"] == "value"
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_query_budget_exceeded(schema_ctx, audit, pdf_renderer, sql_executor):
    tool_use = lambda i: _Response(
        [_ContentToolUse(f"t{i}", "run_query", f"SELECT {i}")],
        stop_reason="tool_use",
    )
    client = FakeAnthropicClient([tool_use(i) for i in range(11)])
    svc = _make_service(client, schema_ctx, audit, pdf_renderer, sql_executor)
    events = [e async for e in svc.stream_turn(SESSION, "loop")]
    errors = [e for e in events if e["type"] == "error"]
    assert errors and "budget" in errors[0]["payload"]["message"].lower()


@pytest.mark.asyncio
async def test_malformed_envelope_emits_error(schema_ctx, audit, pdf_renderer, sql_executor):
    client = FakeAnthropicClient([_Response([_ContentText("not json at all")], stop_reason="end_turn")])
    svc = _make_service(client, schema_ctx, audit, pdf_renderer, sql_executor)
    events = [e async for e in svc.stream_turn(SESSION, "x")]
    assert any(e["type"] == "error" for e in events)


@pytest.mark.asyncio
async def test_report_block_gets_id_and_pdf_url(schema_ctx, audit, pdf_renderer, sql_executor):
    env = json.dumps({
        "blocks": [{"kind": "report", "title": "T", "html": "<p>x</p>"}],
        "citations": [],
    })
    client = FakeAnthropicClient([_Response([_ContentText(env)], stop_reason="end_turn")])
    svc = _make_service(client, schema_ctx, audit, pdf_renderer, sql_executor)
    events = [e async for e in svc.stream_turn(SESSION, "report me")]
    report_blocks = [e for e in events if e["type"] == "block" and e["payload"]["kind"] == "report"]
    assert len(report_blocks) == 1
    p = report_blocks[0]["payload"]
    assert p["id"].startswith("r_")
    assert p["pdf_url"] == f"/report/{p['id']}/pdf"


def test_reset_clears_history(schema_ctx, audit, pdf_renderer, sql_executor):
    client = FakeAnthropicClient([])
    svc = _make_service(client, schema_ctx, audit, pdf_renderer, sql_executor)
    svc._get_or_create_history(SESSION).append({"role": "user", "content": "old"})
    svc.reset(SESSION)
    assert svc.history(SESSION) == []


def test_reset_without_session_clears_all(schema_ctx, audit, pdf_renderer, sql_executor):
    client = FakeAnthropicClient([])
    svc = _make_service(client, schema_ctx, audit, pdf_renderer, sql_executor)
    svc._get_or_create_history("s1").append({"role": "user", "content": "a"})
    svc._get_or_create_history("s2").append({"role": "user", "content": "b"})
    svc.reset()
    assert svc.history("s1") == []
    assert svc.history("s2") == []


@pytest.mark.asyncio
async def test_sessions_are_isolated(schema_ctx, audit, pdf_renderer, sql_executor):
    final = json.dumps({"blocks": [{"kind": "text", "markdown": "x"}], "citations": []})
    client = FakeAnthropicClient([
        _Response([_ContentText(final)], stop_reason="end_turn"),
        _Response([_ContentText(final)], stop_reason="end_turn"),
    ])
    svc = _make_service(client, schema_ctx, audit, pdf_renderer, sql_executor)
    [_ async for _ in svc.stream_turn("s_alice", "hi")]
    [_ async for _ in svc.stream_turn("s_bob", "hi")]
    alice = svc.history("s_alice")
    bob = svc.history("s_bob")
    assert alice and bob and alice is not bob


@pytest.mark.asyncio
async def test_parallel_tool_calls_execute_concurrently(
    schema_ctx, audit, pdf_renderer, sql_executor, monkeypatch
):
    import time
    call_starts: list[float] = []

    def slow_run_query(sql: str):
        call_starts.append(time.monotonic())
        time.sleep(0.1)
        from logic.chat.sql_executor import QueryResult
        return QueryResult(columns=["x"], rows=[[1]], row_count=1, truncated=False, duration_ms=100)

    monkeypatch.setattr(sql_executor, "run_query", slow_run_query)

    final = json.dumps({"blocks": [{"kind": "text", "markdown": "done"}], "citations": []})
    client = FakeAnthropicClient([
        _Response(
            [
                _ContentToolUse("t1", "run_query", "SELECT 1"),
                _ContentToolUse("t2", "run_query", "SELECT 2"),
                _ContentToolUse("t3", "run_query", "SELECT 3"),
            ],
            stop_reason="tool_use",
        ),
        _Response([_ContentText(final)], stop_reason="end_turn"),
    ])
    svc = _make_service(client, schema_ctx, audit, pdf_renderer, sql_executor)

    start = time.monotonic()
    [_ async for _ in svc.stream_turn(SESSION, "do all")]
    elapsed = time.monotonic() - start

    assert len(call_starts) == 3
    assert elapsed < 0.25  # sequential would be ~0.3s
