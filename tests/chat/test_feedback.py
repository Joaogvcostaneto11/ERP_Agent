# tests/chat/test_feedback.py
from __future__ import annotations
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from logic.chat import app as app_module


class _FakeSession:
    def execute(self, stmt) -> Any:
        class _R:
            def keys(self_inner): return []
            def fetchall(self_inner): return []
        return _R()


@contextmanager
def _factory() -> Iterator[_FakeSession]:
    yield _FakeSession()


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> Iterator[TestClient]:
    schema = tmp_path / "schema.md"
    schema.write_text("SCHEMA", encoding="utf-8")
    monkeypatch.setattr(app_module, "_SCHEMA_PATH", schema)
    monkeypatch.setattr(app_module, "_KNOWLEDGE_PATH", tmp_path / "query_knowledge.md")
    monkeypatch.setattr(app_module, "_LOG_PATH", tmp_path / "queries.jsonl")
    monkeypatch.setattr(app_module, "_HISTORY_PATH", tmp_path / "history.sqlite")
    monkeypatch.setattr(app_module, "_session_factory", _factory)
    monkeypatch.setattr(app_module, "_build_anthropic_client", lambda: SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
            content=[SimpleNamespace(type="text", text="### Net sales\n- **Business rule:** subtract credit notes")],
            usage=None,
        ))
    ))
    monkeypatch.setenv("CHAT_FEEDBACK_TOKEN", "s3cret")
    app_module.reset_service()
    with TestClient(app_module.app) as c:
        yield c


def test_enabled_true_when_token_set(client):
    assert client.get("/feedback/enabled").json() == {"enabled": True}


def test_draft_requires_token(client):
    r = client.post("/feedback/draft", json={"question": "q", "sql": "s", "explanation": "e"})
    assert r.status_code == 403


def test_draft_returns_entry_with_token(client):
    r = client.post("/feedback/draft",
                    headers={"X-Feedback-Token": "s3cret"},
                    json={"question": "net sales?", "sql": "SELECT 1", "explanation": "subtract credit notes"})
    assert r.status_code == 200
    assert "subtract credit notes" in r.json()["entry"]


def test_save_appends_and_audits(client, tmp_path: Path):
    r = client.post("/feedback/save",
                    headers={"X-Feedback-Token": "s3cret"},
                    json={"entry": "### Net sales\n- **Business rule:** subtract credit notes",
                          "question": "net sales?", "explanation": "subtract credit notes",
                          "source_turn_id": "t_1", "conversation_id": "c_1"})
    assert r.status_code == 200
    assert r.json()["ke_id"] == "KE-0001"
    # file written
    kfile = tmp_path / "query_knowledge.md"
    assert "### KE-0001 — Net sales" in kfile.read_text(encoding="utf-8")
    # audit line written
    lines = (tmp_path / "queries.jsonl").read_text(encoding="utf-8").splitlines()
    entries = [json.loads(l) for l in lines]
    assert any(e.get("kind") == "knowledge_entry" and e.get("ke_id") == "KE-0001" for e in entries)


def test_disabled_when_no_token(tmp_path: Path, monkeypatch):
    schema = tmp_path / "schema.md"; schema.write_text("S", encoding="utf-8")
    monkeypatch.setattr(app_module, "_SCHEMA_PATH", schema)
    monkeypatch.setattr(app_module, "_KNOWLEDGE_PATH", tmp_path / "k.md")
    monkeypatch.setattr(app_module, "_LOG_PATH", tmp_path / "q.jsonl")
    monkeypatch.setattr(app_module, "_HISTORY_PATH", tmp_path / "h.sqlite")
    monkeypatch.setattr(app_module, "_session_factory", _factory)
    monkeypatch.delenv("CHAT_FEEDBACK_TOKEN", raising=False)
    app_module.reset_service()
    with TestClient(app_module.app) as c:
        assert c.get("/feedback/enabled").json() == {"enabled": False}
        r = c.post("/feedback/draft", json={"question": "q", "sql": "s", "explanation": "e"})
        assert r.status_code == 404
