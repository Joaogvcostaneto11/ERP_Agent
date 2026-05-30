from __future__ import annotations
import asyncio
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from logic.chat.audit import AuditLog
from logic.chat.report_store import ReportStore
from logic.chat.schema_context import SchemaContext
from logic.chat.service import ChatService
from logic.chat.sql_executor import SqlExecutor


SESSION = "s_test"
CONV = "c_test12345678"


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
def report_store() -> ReportStore:
    return ReportStore()


@pytest.fixture
def sql_executor() -> SqlExecutor:
    return SqlExecutor(_factory)


@pytest.fixture
def history(tmp_path: Path):
    from logic.chat.history import HistoryStore
    store = HistoryStore(tmp_path / "history.sqlite")
    # Pre-create the conversation the tests use, so they can call stream_turn directly.
    store._conn.execute(
        "INSERT INTO conversation (id, session_id, title, created_at, updated_at) VALUES (?, ?, '', ?, ?)",
        (CONV, SESSION, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
    )
    store._conn.commit()
    try:
        yield store
    finally:
        store.close()


def _make_service(client, schema_ctx, audit, report_store, sql_executor, history) -> ChatService:
    return ChatService(
        anthropic_client=client,
        sql_executor=sql_executor,
        audit=audit,
        schema_context=schema_ctx,
        report_store=report_store,
        history=history,
        model="claude-sonnet-4-6",
    )


# --- tests ---

@pytest.mark.asyncio
async def test_immediate_text_reply_no_tool_use(schema_ctx, audit, report_store, sql_executor, history):
    envelope_json = json.dumps({"blocks": [{"kind": "text", "markdown": "hi"}], "citations": []})
    client = FakeAnthropicClient([_Response([_ContentText(envelope_json)], stop_reason="end_turn")])
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    events = [e async for e in svc.stream_turn(CONV, SESSION, "hello")]
    types = [e["type"] for e in events]
    assert types[0] == "status"
    assert "block" in types
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_tool_use_round_trip(schema_ctx, audit, report_store, sql_executor, history):
    final = json.dumps({"blocks": [{"kind": "value", "label": "n", "value": 42}], "citations": []})
    client = FakeAnthropicClient([
        _Response([_ContentToolUse("t1", "run_query", "SELECT 42 AS n")], stop_reason="tool_use"),
        _Response([_ContentText(final)], stop_reason="end_turn"),
    ])
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    events = [e async for e in svc.stream_turn(CONV, SESSION, "count")]
    statuses = [e for e in events if e["type"] == "status"]
    blocks = [e for e in events if e["type"] == "block"]
    steps = [e for e in events if e["type"] == "step"]
    assert any(s["payload"].get("phase") == "querying" for s in statuses)
    assert len(blocks) == 1 and blocks[0]["payload"]["kind"] == "value"
    assert len(client.calls) == 2
    # One query step was emitted with SQL + result metadata + row sample
    query_steps = [s for s in steps if s["payload"]["type"] == "query"]
    assert len(query_steps) == 1
    qs = query_steps[0]["payload"]
    assert qs["sql"] == "SELECT 42 AS n"
    assert qs["columns"] == ["n"]
    assert qs["rows_preview"] == [[42]]
    assert qs["error_code"] is None
    # Steps are persisted with the turn
    detail = history.get_conversation(CONV, SESSION)
    assert detail.turns[0].steps == [s["payload"] for s in steps]


@pytest.mark.asyncio
async def test_malformed_envelope_emits_error(schema_ctx, audit, report_store, sql_executor, history):
    client = FakeAnthropicClient([_Response([_ContentText("not json at all")], stop_reason="end_turn")])
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    events = [e async for e in svc.stream_turn(CONV, SESSION, "x")]
    assert any(e["type"] == "error" for e in events)


@pytest.mark.asyncio
async def test_report_block_gets_id_and_view_url(schema_ctx, audit, report_store, sql_executor, history):
    env = json.dumps({
        "blocks": [{"kind": "report", "title": "T", "html": "<p>x</p>"}],
        "citations": [],
    })
    client = FakeAnthropicClient([_Response([_ContentText(env)], stop_reason="end_turn")])
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    events = [e async for e in svc.stream_turn(CONV, SESSION, "report me")]
    report_blocks = [e for e in events if e["type"] == "block" and e["payload"]["kind"] == "report"]
    assert len(report_blocks) == 1
    p = report_blocks[0]["payload"]
    assert p["id"].startswith("r_")
    assert p["view_url"] == f"/report/{p['id']}/view"


@pytest.mark.asyncio
async def test_parallel_tool_calls_execute_concurrently(
    schema_ctx, audit, report_store, sql_executor, history, monkeypatch
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
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)

    start = time.monotonic()
    [_ async for _ in svc.stream_turn(CONV, SESSION, "do all")]
    elapsed = time.monotonic() - start

    assert len(call_starts) == 3
    assert elapsed < 0.25  # sequential would be ~0.3s


@pytest.mark.asyncio
async def test_continues_conversation_from_persisted_transcript(
    schema_ctx, audit, report_store, sql_executor, history
):
    history.append_turn(
        CONV, SESSION, "first question", [{"kind": "text", "markdown": "first answer"}], [], [],
        [{"role": "user", "content": "first question"},
         {"role": "assistant", "content": '{"blocks":[{"kind":"text","markdown":"first answer"}],"citations":[]}'}],
    )
    final = json.dumps({"blocks": [{"kind": "text", "markdown": "follow up"}], "citations": []})
    client = FakeAnthropicClient([_Response([_ContentText(final)], stop_reason="end_turn")])
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    [_ async for _ in svc.stream_turn(CONV, SESSION, "second question")]
    # Claude must have seen the prior turn in messages
    last_call = client.calls[-1]
    contents = [m["content"] for m in last_call["messages"]]
    assert any("first question" in (c if isinstance(c, str) else "") for c in contents)


@pytest.mark.asyncio
async def test_blocks_persisted_after_turn(schema_ctx, audit, report_store, sql_executor, history):
    final = json.dumps({"blocks": [{"kind": "value", "label": "n", "value": 7}], "citations": []})
    client = FakeAnthropicClient([_Response([_ContentText(final)], stop_reason="end_turn")])
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    [_ async for _ in svc.stream_turn(CONV, SESSION, "give me 7")]
    detail = history.get_conversation(CONV, SESSION)
    assert len(detail.turns) == 1
    assert detail.turns[0].blocks == [{"kind": "value", "label": "n", "value": 7, "unit": None}]


@pytest.mark.asyncio
async def test_unauthorized_conversation_emits_error(
    schema_ctx, audit, report_store, sql_executor, history
):
    client = FakeAnthropicClient([])
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    events = [e async for e in svc.stream_turn(CONV, "s_someone_else", "hi")]
    err = [e for e in events if e["type"] == "error"]
    assert err and err[0]["payload"]["code"] == "unauthorized"
    assert len(client.calls) == 0  # Claude never called


@pytest.mark.asyncio
async def test_title_generation_fires_after_first_turn(
    schema_ctx, audit, report_store, sql_executor, history
):
    final = json.dumps({"blocks": [{"kind": "text", "markdown": "hello back"}], "citations": []})
    title_response = _Response([_ContentText("Friendly greeting exchanged")], stop_reason="end_turn")

    class _Client:
        def __init__(self):
            self.calls: list[dict] = []
            self.messages = SimpleNamespace(create=self._create)
            self._main = [_Response([_ContentText(final)], stop_reason="end_turn")]
            self._title = [title_response]

        def _create(self, **kw):
            self.calls.append(kw)
            if kw.get("model", "").startswith("claude-haiku"):
                return self._title.pop(0)
            return self._main.pop(0)

    client = _Client()
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    [_ async for _ in svc.stream_turn(CONV, SESSION, "hello")]
    # The background task may not have finished by the time stream_turn returns.
    # Drain pending tasks to give it a chance.
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    detail = history.get_conversation(CONV, SESSION)
    assert detail.title == "Friendly greeting exchanged"
