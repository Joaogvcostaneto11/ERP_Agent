from __future__ import annotations
import os
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
    # We expect at least one status, one block, and one done event.
    assert "event: status" in body
    assert "event: block" in body
    assert "event: done" in body
