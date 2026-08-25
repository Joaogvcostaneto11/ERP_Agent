import importlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")  # service build will be mocked off
    monkeypatch.setenv("DEVCARE_HISTORY_PATH", str(tmp_path / "h.sqlite"))
    monkeypatch.setenv("DEVCARE_WRITE_LOG_PATH", str(tmp_path / "w.jsonl"))
    from logic.devcare import app as appmod
    importlib.reload(appmod)
    return TestClient(appmod.app)


def test_set_operator_then_conversations(client):
    r = client.post("/devcare/operator", json={"name": "Joao"})
    assert r.status_code == 200
    r = client.post("/devcare/conversations")
    assert r.status_code == 200 and r.json()["id"]


def test_operations_requires_operator(client):
    r = client.post("/devcare/conversations")
    cid = r.json()["id"]
    # no operator set on a fresh client cookie jar -> 400
    client.cookies.clear()
    r = client.post("/devcare/operations", json={"conversation_id": cid, "message": "hi"})
    assert r.status_code in (400, 401)


def test_commit_unknown_change_returns_error(client):
    client.post("/devcare/operator", json={"name": "Joao"})
    cid = client.post("/devcare/conversations").json()["id"]
    r = client.post(f"/devcare/commit/chg_missing", json={"conversation_id": cid})
    assert r.status_code == 200
    assert r.json()["status"] == "error"


def test_operator_cookie_is_marked_secure_behind_tls(client):
    r = client.post("/devcare/operator", json={"name": "Joao"},
                    headers={"X-Forwarded-Proto": "https"})
    assert "Secure" in r.headers["set-cookie"]


def test_devcare_password_gate(monkeypatch, tmp_path):
    """DevCare writes to the ERP database, so it gets the same shared-password
    gate as the other two services — its own secret, and ungated when unset.

    The gate is installed at import time from the environment, so the module is
    reloaded with the variable set, then reloaded again afterwards.
    """
    import importlib
    from logic.devcare import app as appmod

    monkeypatch.setenv("DEVCARE_HISTORY_PATH", str(tmp_path / "h.sqlite"))
    monkeypatch.setenv("DEVCARE_APP_PASSWORD", "s3cret")
    gated = importlib.reload(appmod)
    try:
        c = TestClient(gated.app)
        assert c.get("/healthz").status_code == 200      # Render's probe stays open
        assert c.post("/devcare/operator", json={"name": "x"}).status_code == 401
    finally:
        # Empty string, not delenv: reload() calls load_dotenv() again and a
        # deleted key gets refilled from the repo's real .env.
        monkeypatch.setenv("DEVCARE_APP_PASSWORD", "")
        importlib.reload(gated)


def test_security_headers_on_devcare(client):
    h = client.post("/devcare/operator", json={"name": "x"}).headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
