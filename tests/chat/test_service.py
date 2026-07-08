from __future__ import annotations
import asyncio
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from logic.chat.audit import AuditLog
from logic.chat.knowledge_store import KnowledgeStore
from logic.chat.report_store import ReportStore
from logic.chat.schema_context import SchemaContext
from logic.chat.service import (
    ChatService,
    _compress_past_turns_for_claude,
    _strip_heavy_blocks_from_envelope,
)
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


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int,
                 cache_read_input_tokens: int = 0,
                 cache_creation_input_tokens: int = 0) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = cache_read_input_tokens
        self.cache_creation_input_tokens = cache_creation_input_tokens


class _Response:
    def __init__(self, content: list, stop_reason: str, usage: _Usage | None = None) -> None:
        self.content = content
        self.stop_reason = stop_reason
        if usage is not None:
            self.usage = usage


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
        knowledge_store=KnowledgeStore("/nonexistent/path/knowledge.md"),
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


# --- _compress_past_turns_for_claude unit tests ---

def _u(text: str) -> dict:
    return {"role": "user", "content": text}


def _a(text: str) -> dict:
    return {"role": "assistant", "content": text}


def _a_tooluse(sql: str, tid: str = "t1") -> dict:
    return {"role": "assistant", "content": [
        {"type": "text", "text": "thinking..."},
        {"type": "tool_use", "id": tid, "name": "run_query", "input": {"sql": sql}},
    ]}


def _u_toolresult(tid: str = "t1", payload: str = "{}") -> dict:
    return {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": payload},
    ]}


def test_compress_empty_transcript():
    assert _compress_past_turns_for_claude([]) == []


def test_compress_single_turn_unchanged():
    """The current turn (only turn) is preserved verbatim."""
    transcript = [_u("hi"), _a_tooluse("SELECT 1"), _u_toolresult(), _a("answer")]
    assert _compress_past_turns_for_claude(transcript) == transcript


def test_compress_drops_intermediate_messages_from_past_turn():
    """A past turn collapses to [user question, final assistant string]."""
    past = [_u("first?"), _a_tooluse("SELECT 1"), _u_toolresult(), _a("first answer")]
    current = [_u("second?"), _a_tooluse("SELECT 2"), _u_toolresult()]
    result = _compress_past_turns_for_claude(past + current)
    assert result == [_u("first?"), _a("first answer")] + current


def test_compress_handles_multiple_past_turns():
    t1 = [_u("q1"), _a_tooluse("S1"), _u_toolresult(), _a("a1")]
    t2 = [_u("q2"), _a_tooluse("S2"), _u_toolresult(), _a("a2")]
    t3 = [_u("q3"), _a_tooluse("S3"), _u_toolresult()]  # current, no final yet
    result = _compress_past_turns_for_claude(t1 + t2 + t3)
    assert result == [_u("q1"), _a("a1"), _u("q2"), _a("a2")] + t3


def test_compress_past_turn_without_final_string_keeps_just_user():
    """A past turn that for any reason has no final assistant-string keeps
    only the user question (the rest is dropped)."""
    bad_past = [_u("q1"), _a_tooluse("S1"), _u_toolresult()]
    current = [_u("q2")]
    result = _compress_past_turns_for_claude(bad_past + current)
    assert result == [_u("q1"), _u("q2")]


@pytest.mark.asyncio
async def test_usage_step_emitted_per_claude_call(
    schema_ctx, audit, report_store, sql_executor, history
):
    """Each Claude call surfaces a `usage` step with the response's token counts.
    A two-round turn (tool_use then final) produces two usage steps."""
    tool_round = _Response(
        [_ContentToolUse("t1", "run_query", "SELECT 42 AS n")],
        stop_reason="tool_use",
        usage=_Usage(input_tokens=12345, output_tokens=67,
                     cache_read_input_tokens=10000, cache_creation_input_tokens=0),
    )
    final = json.dumps({"blocks": [{"kind": "value", "label": "n", "value": 42}], "citations": []})
    final_round = _Response(
        [_ContentText(final)],
        stop_reason="end_turn",
        usage=_Usage(input_tokens=12500, output_tokens=200,
                     cache_read_input_tokens=10000),
    )
    client = FakeAnthropicClient([tool_round, final_round])
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    events = [e async for e in svc.stream_turn(CONV, SESSION, "count")]
    usages = [e["payload"] for e in events
              if e["type"] == "step" and e["payload"]["type"] == "usage"]
    assert len(usages) == 2
    assert usages[0]["input_tokens"] == 12345
    assert usages[0]["output_tokens"] == 67
    assert usages[0]["cache_read_input_tokens"] == 10000
    assert usages[1]["input_tokens"] == 12500
    # Each usage step carries an estimated USD cost (model claude-sonnet-4-6).
    # Round 1 = 12345*3 + 67*15 + 10000*0.3 + 0*3.75 = 41040 → $0.04104
    assert usages[0]["cost_usd"] == pytest.approx(0.04104, abs=1e-6)
    # Persisted with the turn's other steps
    detail = history.get_conversation(CONV, SESSION)
    persisted_usages = [s for s in detail.turns[0].steps if s["type"] == "usage"]
    assert len(persisted_usages) == 2
    assert "cost_usd" in persisted_usages[0]


@pytest.mark.asyncio
async def test_turn_summary_logged_with_total_cost(
    schema_ctx, audit, report_store, sql_executor, history
):
    """Every turn writes a single kind=turn_summary row to queries.jsonl
    with aggregated tokens and total USD cost."""
    final = json.dumps({"blocks": [{"kind": "text", "markdown": "ok"}], "citations": []})
    client = FakeAnthropicClient([
        _Response([_ContentText(final)], stop_reason="end_turn",
                  usage=_Usage(input_tokens=100, output_tokens=50,
                               cache_read_input_tokens=5000)),
    ])
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    [_ async for _ in svc.stream_turn(CONV, SESSION, "hi")]
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)

    lines = audit._path.read_text(encoding="utf-8").splitlines()
    summaries = [json.loads(l) for l in lines if json.loads(l).get("kind") == "turn_summary"]
    assert len(summaries) == 1
    s = summaries[0]
    assert s["status"] == "ok"
    assert s["claude_calls"] == 1
    assert s["sql_queries"] == 0
    assert s["total_input_tokens"] == 100
    assert s["total_output_tokens"] == 50
    assert s["total_cache_read_input_tokens"] == 5000
    # 100*3 + 50*15 + 5000*0.3 + 0 = 2550 → $0.00255
    assert s["total_cost_usd"] == pytest.approx(0.00255, abs=1e-6)
    assert s["turn_id"].startswith("t_")
    assert s["conversation_id"] == CONV
    assert s["session_id"] == SESSION


@pytest.mark.asyncio
async def test_turn_summary_records_error_status(
    schema_ctx, audit, report_store, sql_executor, history
):
    """An internal error during the turn still produces a turn_summary
    with status='error'."""
    class _Boom:
        def __init__(self):
            self.calls = []
            self.messages = SimpleNamespace(create=self._create)

        def _create(self, **kw):
            self.calls.append(kw)
            raise RuntimeError("boom")

    svc = _make_service(_Boom(), schema_ctx, audit, report_store, sql_executor, history)
    [_ async for _ in svc.stream_turn(CONV, SESSION, "hi")]

    lines = audit._path.read_text(encoding="utf-8").splitlines()
    summaries = [json.loads(l) for l in lines if json.loads(l).get("kind") == "turn_summary"]
    assert len(summaries) == 1
    assert summaries[0]["status"] == "error"
    # No usage step because the Claude call itself blew up
    assert summaries[0]["total_input_tokens"] == 0


@pytest.mark.asyncio
async def test_turn_summary_records_aborted_on_early_close(
    schema_ctx, audit, report_store, sql_executor, history
):
    """A client disconnect (generator closed mid-turn) raises GeneratorExit,
    which bypasses the except. The turn_summary must record status='aborted',
    not 'ok'."""
    final = json.dumps({"blocks": [{"kind": "text", "markdown": "ok"}], "citations": []})
    client = FakeAnthropicClient([
        _Response([_ContentText(final)], stop_reason="end_turn",
                  usage=_Usage(input_tokens=10, output_tokens=20)),
    ])
    svc = _make_service(client, schema_ctx, audit, report_store, sql_executor, history)
    agen = svc.stream_turn(CONV, SESSION, "hi")
    await agen.__anext__()   # advance past the first yield, then disconnect
    await agen.aclose()

    lines = audit._path.read_text(encoding="utf-8").splitlines()
    summaries = [json.loads(l) for l in lines if json.loads(l).get("kind") == "turn_summary"]
    assert len(summaries) == 1
    assert summaries[0]["status"] == "aborted"


@pytest.mark.asyncio
async def test_usage_step_skips_cost_for_unknown_model(
    schema_ctx, audit, report_store, sql_executor, history
):
    """Unknown model id → usage step still emitted, but without a cost."""
    final = json.dumps({"blocks": [{"kind": "text", "markdown": "ok"}], "citations": []})
    client = FakeAnthropicClient([
        _Response([_ContentText(final)], stop_reason="end_turn",
                  usage=_Usage(input_tokens=10, output_tokens=20)),
    ])
    svc = ChatService(
        anthropic_client=client, sql_executor=sql_executor, audit=audit,
        schema_context=schema_ctx, report_store=report_store, history=history,
        model="some-unreleased-future-model",
        knowledge_store=KnowledgeStore("/nonexistent/path/knowledge.md"),
    )
    events = [e async for e in svc.stream_turn(CONV, SESSION, "hi")]
    usages = [e["payload"] for e in events
              if e["type"] == "step" and e["payload"]["type"] == "usage"]
    assert len(usages) == 1
    assert "cost_usd" not in usages[0]


def test_compress_no_user_string_returns_as_is():
    """Defensive: if there is no turn boundary at all, return unchanged
    (the caller's sanitizer will repair this case separately)."""
    weird = [_a("stray"), _u_toolresult()]
    assert _compress_past_turns_for_claude(weird) == weird


# --- _strip_heavy_blocks_from_envelope unit tests ---

def test_strip_replaces_table_with_summary():
    env = json.dumps({
        "blocks": [{"kind": "table", "columns": ["a", "b"],
                    "rows": [[1, 2], [3, 4], [5, 6]], "caption": "test"}],
        "citations": [],
    })
    out = json.loads(_strip_heavy_blocks_from_envelope(env))
    assert len(out["blocks"]) == 1
    block = out["blocks"][0]
    assert block["kind"] == "text"
    assert "3 rows" in block["markdown"] and "2 cols" in block["markdown"]
    assert "a, b" in block["markdown"]


def test_strip_replaces_chart_with_summary():
    env = json.dumps({
        "blocks": [{"kind": "chart", "title": "Revenue",
                    "plotly": {"data": [{"y": list(range(1000))}], "layout": {}}}],
        "citations": [],
    })
    out = json.loads(_strip_heavy_blocks_from_envelope(env))
    assert out["blocks"][0]["kind"] == "text"
    assert "Revenue" in out["blocks"][0]["markdown"]


def test_strip_replaces_report_with_summary():
    env = json.dumps({
        "blocks": [{"kind": "report", "id": "r_x", "title": "Q4",
                    "html": "<p>" + "x" * 5000 + "</p>", "view_url": "/report/r_x/view"}],
        "citations": [],
    })
    out = json.loads(_strip_heavy_blocks_from_envelope(env))
    assert out["blocks"][0]["kind"] == "text"
    assert "Q4" in out["blocks"][0]["markdown"]
    # Original HTML should be gone
    assert "x" * 100 not in _strip_heavy_blocks_from_envelope(env)


def test_strip_preserves_text_and_value_blocks():
    env = json.dumps({
        "blocks": [
            {"kind": "text", "markdown": "hello"},
            {"kind": "value", "label": "n", "value": 42, "unit": None},
        ],
        "citations": [{"summary": "src", "sql_log_id": None}],
    })
    out = json.loads(_strip_heavy_blocks_from_envelope(env))
    assert out["blocks"][0] == {"kind": "text", "markdown": "hello"}
    assert out["blocks"][1] == {"kind": "value", "label": "n", "value": 42, "unit": None}
    assert out["citations"] == [{"summary": "src", "sql_log_id": None}]


def test_strip_passes_non_envelope_through():
    assert _strip_heavy_blocks_from_envelope("just plain text") == "just plain text"
    assert _strip_heavy_blocks_from_envelope("{not valid json") == "{not valid json"


def test_compress_strips_heavy_blocks_from_past_envelope():
    """End-to-end: a past turn whose final answer was a big table comes out
    of compression as a small text summary."""
    past_env = json.dumps({
        "blocks": [{"kind": "table", "columns": ["x", "y"],
                    "rows": [[i, i*2] for i in range(500)]}],
        "citations": [],
    })
    past = [_u("q1"), _a_tooluse("S"), _u_toolresult(), _a(past_env)]
    current = [_u("q2")]
    result = _compress_past_turns_for_claude(past + current)
    # Past assistant's content should now be a small summary, not the 500 rows
    past_answer = result[1]["content"]
    assert "500 rows" in past_answer
    # Original 500 rows are gone — file should be much smaller than the input
    assert len(past_answer) < 500
    assert len(past_answer) < len(past_env)
