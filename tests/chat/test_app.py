from __future__ import annotations
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
    monkeypatch.setenv("CHAT_VOICE_LANG", "en-US")
    monkeypatch.setattr(app_module, "_SCHEMA_PATH", schema)
    monkeypatch.setattr(app_module, "_LOG_PATH", tmp_path / "queries.jsonl")
    monkeypatch.setattr(app_module, "_session_factory", _factory)
    monkeypatch.setattr(app_module, "_build_anthropic_client", lambda: SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kw: SimpleNamespace(
            content=[SimpleNamespace(type="text", text='{"blocks":[{"kind":"text","markdown":"hi"}],"citations":[]}')],
            stop_reason="end_turn",
        ))
    ))
    app_module.reset_service()
    with TestClient(app_module.app) as c:
        yield c


def test_config_returns_voice_lang(client):
    r = client.get("/config")
    assert r.status_code == 200
    assert r.json() == {"voice_lang": "en-US"}


def test_chat_reset(client):
    r = client.post("/chat/reset")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_report_pdf_404_for_unknown(client):
    r = client.get("/report/r_nope/pdf")
    assert r.status_code == 404


def test_static_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<!doctype html" in r.text.lower() or "<html" in r.text.lower()


def test_chat_sse_streams_envelope(client):
    with client.stream("POST", "/chat", json={"message": "hi"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = b"".join(r.iter_bytes()).decode("utf-8")
    assert "event: status" in body
    assert "event: block" in body
    assert "event: done" in body


def test_chat_sets_session_cookie(client):
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 200
    assert "chat_session" in r.cookies
    assert r.cookies["chat_session"].startswith("s_")


def test_chat_reuses_session_cookie(client):
    r1 = client.post("/chat", json={"message": "first"})
    sid = r1.cookies["chat_session"]
    # Second request should reuse the cookie set on the first
    r2 = client.post("/chat", json={"message": "second"})
    assert r2.cookies.get("chat_session", sid) == sid


def test_chat_missing_api_key_streams_config_error(tmp_path: Path, monkeypatch):
    schema = tmp_path / "schema.md"
    schema.write_text("SCHEMA", encoding="utf-8")
    monkeypatch.setattr(app_module, "_SCHEMA_PATH", schema)
    monkeypatch.setattr(app_module, "_LOG_PATH", tmp_path / "queries.jsonl")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app_module.reset_service()
    with TestClient(app_module.app) as c:
        with c.stream("POST", "/chat", json={"message": "hi"}) as r:
            body = b"".join(r.iter_bytes()).decode("utf-8")
    assert "event: error" in body
    assert "ANTHROPIC_API_KEY" in body
