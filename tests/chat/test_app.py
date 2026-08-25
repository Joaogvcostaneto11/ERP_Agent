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
    monkeypatch.setattr(app_module, "_SCHEMA_PATH", schema)
    monkeypatch.setattr(app_module, "_LOG_PATH", tmp_path / "queries.jsonl")
    monkeypatch.setattr(app_module, "_HISTORY_PATH", tmp_path / "history.sqlite")
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


def test_report_view_404_for_unknown(client):
    r = client.get("/report/r_nope/view")
    assert r.status_code == 404


def test_report_view_returns_print_styled_html(client):
    # Register a report via the service directly so we have a known id
    svc = app_module.get_service()
    rid = svc._reports.register("<p>Hello</p>", "My Report")
    r = client.get(f"/report/{rid}/view")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    assert "My Report" in body
    assert "<p>Hello</p>" in body
    assert "report.css" in body  # print-styled link tag


def test_static_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<!doctype html" in r.text.lower() or "<html" in r.text.lower()


def test_index_version_stamps_assets(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert "/app.js?v=" in r.text
    assert "chat.css?v=" in r.text


def test_chat_sse_streams_envelope(client):
    cid = client.post("/conversations").json()["id"]
    with client.stream("POST", "/chat", json={"conversation_id": cid, "message": "hi"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = b"".join(r.iter_bytes()).decode("utf-8")
    assert "event: status" in body
    assert "event: block" in body
    assert "event: done" in body


def test_chat_sets_session_cookie(client):
    cid = client.post("/conversations").json()["id"]
    r = client.post("/chat", json={"conversation_id": cid, "message": "hi"})
    assert r.status_code == 200
    assert "chat_session" in r.cookies
    assert r.cookies["chat_session"].startswith("s_")


def test_chat_reuses_session_cookie(client):
    cid = client.post("/conversations").json()["id"]
    r1 = client.post("/chat", json={"conversation_id": cid, "message": "first"})
    sid = r1.cookies["chat_session"]
    r2 = client.post("/chat", json={"conversation_id": cid, "message": "second"})
    assert r2.cookies.get("chat_session", sid) == sid


def test_create_conversation_returns_id(client):
    r = client.post("/conversations")
    assert r.status_code == 200
    body = r.json()
    assert body["id"].startswith("c_")
    assert "chat_session" in r.cookies


def test_list_conversations_session_scoped(client):
    a = client.post("/conversations").json()["id"]
    rows = client.get("/conversations").json()["conversations"]
    assert any(r["id"] == a for r in rows)


def test_get_conversation_owner(client):
    a = client.post("/conversations").json()["id"]
    r = client.get(f"/conversations/{a}")
    assert r.status_code == 200
    assert r.json()["id"] == a


def test_get_conversation_cross_session_404(client):
    a = client.post("/conversations").json()["id"]
    fresh = TestClient(app_module.app)
    r = fresh.get(f"/conversations/{a}")
    assert r.status_code == 404


def test_delete_conversation_owner(client):
    a = client.post("/conversations").json()["id"]
    r = client.delete(f"/conversations/{a}")
    assert r.status_code == 204
    assert client.get(f"/conversations/{a}").status_code == 404


def test_delete_conversation_cross_session_404(client):
    a = client.post("/conversations").json()["id"]
    fresh = TestClient(app_module.app)
    assert fresh.delete(f"/conversations/{a}").status_code == 404


def test_chat_unauthorized_conversation_id(client):
    with client.stream("POST", "/chat", json={"conversation_id": "c_doesnotexist", "message": "hi"}) as r:
        body = b"".join(r.iter_bytes()).decode("utf-8")
    assert "event: error" in body
    assert "unauthorized" in body


def test_chat_missing_conversation_id_returns_400(client):
    r = client.post("/chat", json={"message": "hi"})
    assert r.status_code == 400


def test_chat_missing_api_key_streams_config_error(tmp_path: Path, monkeypatch):
    schema = tmp_path / "schema.md"
    schema.write_text("SCHEMA", encoding="utf-8")
    monkeypatch.setattr(app_module, "_SCHEMA_PATH", schema)
    monkeypatch.setattr(app_module, "_LOG_PATH", tmp_path / "queries.jsonl")
    monkeypatch.setattr(app_module, "_HISTORY_PATH", tmp_path / "history.sqlite")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    app_module.reset_service()
    with TestClient(app_module.app) as c:
        with c.stream("POST", "/chat", json={"conversation_id": "c_anything", "message": "hi"}) as r:
            body = b"".join(r.iter_bytes()).decode("utf-8")
    assert "event: error" in body
    assert "ANTHROPIC_API_KEY" in body


@pytest.mark.asyncio
async def test_keepalive_emitted_while_turn_is_silent(monkeypatch):
    """A turn that blocks (a slow Claude call, or retry backoff) must keep the
    SSE connection warm, or a proxy's idle-read timeout kills it before the
    error event arrives."""
    import asyncio

    monkeypatch.setattr(app_module, "_KEEPALIVE_SECONDS", 0.01)

    async def slow():
        await asyncio.sleep(0.05)
        yield b"event: done\ndata: {}\n\n"

    chunks = [c async for c in app_module._with_keepalive(slow())]
    assert chunks[-1] == b"event: done\ndata: {}\n\n"
    assert chunks.count(app_module._KEEPALIVE) >= 1
    # Only comments are injected — no extra data frames the client would render
    assert [c for c in chunks if c != app_module._KEEPALIVE] == [chunks[-1]]


@pytest.mark.asyncio
async def test_keepalive_passes_events_through_unchanged(monkeypatch):
    """With no stall the wrapper is transparent."""
    monkeypatch.setattr(app_module, "_KEEPALIVE_SECONDS", 30.0)

    async def fast():
        yield b"a"
        yield b"b"

    assert [c async for c in app_module._with_keepalive(fast())] == [b"a", b"b"]


# Report HTML is written by the model, so the print view must treat it exactly
# as the browser renderer does (ui/chat/renderers/report.js runs it through
# DOMPurify) rather than trusting it because it arrived server-side.
@pytest.mark.parametrize("html,gone", [
    ("<p>ok</p><script>alert(1)</script>", "alert(1)"),
    ('<img src=x onerror="alert(1)">', "onerror"),
    ('<a href="javascript:alert(1)">x</a>', "javascript:"),
    ('<iframe src="https://evil.example"></iframe>', "iframe"),
    ('<p onclick="alert(1)">x</p>', "onclick"),
])
def test_report_view_strips_active_content(client, html, gone):
    svc = app_module.get_service()
    rid = svc._reports.register(html, "R")
    body = client.get(f"/report/{rid}/view").text
    assert gone not in body


def test_report_view_keeps_report_markup(client):
    svc = app_module.get_service()
    rid = svc._reports.register(
        '<h2>Totals</h2><table class="t"><tr><td>1</td></tr></table>', "R")
    body = client.get(f"/report/{rid}/view").text
    assert "<h2>Totals</h2>" in body
    assert "<td>1</td>" in body


def test_report_view_forbids_scripting_via_csp(client):
    svc = app_module.get_service()
    rid = svc._reports.register("<p>ok</p>", "R")
    csp = client.get(f"/report/{rid}/view").headers.get("content-security-policy", "")
    assert "script-src 'none'" in csp


def test_session_cookie_is_marked_secure_behind_tls(client):
    # The gate and this cookie are all that separate one operator's
    # conversations from another's, so it must not travel in clear.
    r = client.post("/conversations", headers={"X-Forwarded-Proto": "https"})
    assert "Secure" in r.headers["set-cookie"]


def test_security_headers_on_chat(client):
    h = client.get("/conversations").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    # The CDN scripts in ui/chat/index.html have to stay loadable.
    assert "https://cdn.jsdelivr.net" in h["Content-Security-Policy"]


def test_report_view_keeps_its_stricter_csp(client):
    svc = app_module.get_service()
    rid = svc._reports.register("<p>ok</p>", "R")
    csp = client.get(f"/report/{rid}/view").headers["Content-Security-Policy"]
    assert "script-src 'none'" in csp, "app baseline must not relax the report view"
