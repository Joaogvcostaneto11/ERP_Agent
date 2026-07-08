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
