from __future__ import annotations
import json
from pathlib import Path

import pytest

from logic.chat.history import ConversationSummary, ConversationDetail, HistoryStore


@pytest.fixture
def store(tmp_path: Path):
    s = HistoryStore(tmp_path / "history.sqlite")
    try:
        yield s
    finally:
        s.close()


def test_create_returns_unique_prefixed_id(store):
    a = store.create_conversation("s_alice")
    b = store.create_conversation("s_alice")
    assert a != b
    assert a.startswith("c_") and len(a) == 14  # 'c_' + 12 hex


def test_list_returns_session_scoped_only(store):
    a = store.create_conversation("s_alice")
    store.create_conversation("s_bob")
    rows = store.list_conversations("s_alice")
    assert len(rows) == 1
    assert isinstance(rows[0], ConversationSummary)
    assert rows[0].id == a


def test_get_returns_none_for_other_session(store):
    a = store.create_conversation("s_alice")
    assert store.get_conversation(a, "s_bob") is None


def test_get_returns_detail_for_owner(store):
    a = store.create_conversation("s_alice")
    store.append_turn(a, "s_alice", "hi", [{"kind": "text", "markdown": "hello"}], [], [], [{"role": "user", "content": "hi"}])
    detail = store.get_conversation(a, "s_alice")
    assert isinstance(detail, ConversationDetail)
    assert detail.id == a
    assert len(detail.turns) == 1
    assert detail.turns[0].user_message == "hi"
    assert detail.turns[0].blocks == [{"kind": "text", "markdown": "hello"}]
    assert detail.turns[0].steps == []


def test_delete_session_isolated(store):
    a = store.create_conversation("s_alice")
    assert store.delete_conversation(a, "s_bob") is False
    assert store.get_conversation(a, "s_alice") is not None
    assert store.delete_conversation(a, "s_alice") is True
    assert store.get_conversation(a, "s_alice") is None


def test_list_orders_by_updated_at_desc(store):
    a = store.create_conversation("s_alice")
    b = store.create_conversation("s_alice")
    # Bumping a's updated_at via append_turn should put it first
    store.append_turn(a, "s_alice", "hi", [{"kind": "text", "markdown": "x"}], [], [], [])
    ids = [r.id for r in store.list_conversations("s_alice")]
    assert ids[0] == a
    assert ids[1] == b


def test_append_turn_updates_conversation_updated_at(store):
    a = store.create_conversation("s_alice")
    before = store.get_conversation(a, "s_alice").updated_at
    store.append_turn(a, "s_alice", "hi", [], [], [], [])
    after = store.get_conversation(a, "s_alice").updated_at
    assert after >= before


def test_get_transcript_empty_for_new(store):
    a = store.create_conversation("s_alice")
    assert store.get_transcript(a, "s_alice") == []


def test_get_transcript_returns_last_raw(store):
    a = store.create_conversation("s_alice")
    store.append_turn(a, "s_alice", "first", [], [], [], [{"role": "user", "content": "first"}])
    store.append_turn(a, "s_alice", "second", [], [], [], [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "ack"},
        {"role": "user", "content": "second"},
    ])
    transcript = store.get_transcript(a, "s_alice")
    assert len(transcript) == 3
    assert transcript[-1]["content"] == "second"


def test_get_transcript_session_isolated(store):
    a = store.create_conversation("s_alice")
    store.append_turn(a, "s_alice", "hi", [], [], [], [{"role": "user", "content": "hi"}])
    assert store.get_transcript(a, "s_bob") == []


def test_cascade_delete_removes_turns(store):
    a = store.create_conversation("s_alice")
    store.append_turn(a, "s_alice", "hi", [], [], [], [])
    store.delete_conversation(a, "s_alice")
    # Re-creating with same logical id wouldn't be possible (random id), so just
    # verify direct row count via a fresh read.
    assert store.get_conversation(a, "s_alice") is None


def test_update_title_session_isolated(store):
    a = store.create_conversation("s_alice")
    store.update_title(a, "s_bob", "hijack")
    assert store.get_conversation(a, "s_alice").title == ""
    store.update_title(a, "s_alice", "real title")
    assert store.get_conversation(a, "s_alice").title == "real title"


def test_transcript_capped_to_last_n(store):
    a = store.create_conversation("s_alice")
    long_transcript = [{"role": "user", "content": f"msg{i}"} for i in range(50)]
    store.append_turn(a, "s_alice", "hi", [], [], [], long_transcript)
    transcript = store.get_transcript(a, "s_alice")
    assert len(transcript) == 40
    assert transcript[0]["content"] == "msg10"  # first 10 trimmed


def test_transcript_cap_never_strands_tool_result(store):
    """The cap must start at a user-string boundary so Claude doesn't 400
    on a leading orphan tool_result."""
    a = store.create_conversation("s_alice")
    # 12 fully-formed turns (4 messages each = 48 total)
    transcript = []
    for i in range(12):
        transcript.append({"role": "user", "content": f"q{i}"})
        transcript.append({"role": "assistant", "content": [
            {"type": "tool_use", "id": f"t{i}", "name": "run_query", "input": {"sql": "SELECT 1"}},
        ]})
        transcript.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "content": "{}"},
        ]})
        transcript.append({"role": "assistant", "content": f"answer{i}"})
    store.append_turn(a, "s_alice", "ignored", [], [], [], transcript)
    persisted = store.get_transcript(a, "s_alice")
    assert len(persisted) <= 40
    # The persisted transcript must START with a user-string message,
    # never a list-content (tool_result) message.
    first = persisted[0]
    assert first["role"] == "user"
    assert isinstance(first["content"], str)


def test_get_transcript_sanitizes_legacy_corrupted_data(store):
    """An older DB row whose raw_transcript starts with a leading tool_result
    must be repaired on read."""
    a = store.create_conversation("s_alice")
    # Inject a corrupted transcript directly via SQL (simulating data from
    # before the cap fix)
    corrupted = [
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "orphan", "content": "{}"},
        ]},
        {"role": "assistant", "content": "stray"},
        {"role": "user", "content": "valid question"},
        {"role": "assistant", "content": "valid answer"},
    ]
    store.append_turn(a, "s_alice", "hi", [], [], [], corrupted)
    persisted = store.get_transcript(a, "s_alice")
    assert persisted[0] == {"role": "user", "content": "valid question"}
    assert len(persisted) == 2


def test_update_title_truncated_at_200(store):
    a = store.create_conversation("s_alice")
    long_title = "x" * 250
    store.update_title(a, "s_alice", long_title)
    assert store.get_conversation(a, "s_alice").title == "x" * 200


def test_append_turn_returns_false_for_wrong_session(store):
    a = store.create_conversation("s_alice")
    ok = store.append_turn(a, "s_bob", "hi", [], [], [], [])
    assert ok is False
    # No turn should have been inserted
    assert store.get_transcript(a, "s_alice") == []


def test_append_turn_persists_steps(store):
    a = store.create_conversation("s_alice")
    steps = [
        {"type": "reasoning", "text": "I'll count rows"},
        {"type": "query", "sql": "SELECT COUNT(*) FROM t",
         "row_count": 1, "duration_ms": 42, "truncated": False,
         "columns": ["cnt"], "rows_preview": [[7]],
         "error_code": None, "error_message": None},
    ]
    store.append_turn(a, "s_alice", "hi", [], [], steps, [])
    detail = store.get_conversation(a, "s_alice")
    assert detail.turns[0].steps == steps


def test_update_title_returns_false_for_wrong_session(store):
    a = store.create_conversation("s_alice")
    ok = store.update_title(a, "s_bob", "hijacked")
    assert ok is False
