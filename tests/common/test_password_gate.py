import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from logic.common.password_gate import install_password_gate


def _app(password, **kw):
    app = FastAPI()

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.get("/private")
    def private():
        return {"secret": True}

    install_password_gate(app, password, realm="Test Realm", **kw)
    return TestClient(app)


def _auth(user, pw):
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.mark.parametrize("password", [None, ""])
def test_no_password_installs_no_gate(password):
    # Local dev and the whole existing test suite depend on this.
    client = _app(password)
    assert client.get("/private").status_code == 200


def test_missing_credentials_are_rejected():
    r = _app("s3cret").get("/private")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == 'Basic realm="Test Realm"'


def test_wrong_password_is_rejected():
    r = _app("s3cret").get("/private", headers=_auth("someone", "wrong"))
    assert r.status_code == 401


def test_correct_password_passes():
    r = _app("s3cret").get("/private", headers=_auth("someone", "s3cret"))
    assert r.status_code == 200


def test_username_is_ignored():
    # The deployment shares one secret rather than issuing accounts.
    client = _app("s3cret")
    for user in ("", "alice", "root"):
        assert client.get("/private", headers=_auth(user, "s3cret")).status_code == 200


def test_healthz_is_exempt_by_default():
    # Render's health check is unauthenticated; a 401 here means the service
    # never goes live.
    assert _app("s3cret").get("/healthz").status_code == 200


def test_exempt_paths_are_configurable():
    client = _app("s3cret", exempt={"/private"})
    assert client.get("/private").status_code == 200
    assert client.get("/healthz").status_code == 401


@pytest.mark.parametrize("header", [
    "Bearer abc", "Basic", "Basic !!!not-base64!!!", "Basic " + base64.b64encode(b"no-colon").decode(),
])
def test_malformed_authorization_headers_are_rejected_without_raising(header):
    r = _app("s3cret").get("/private", headers={"Authorization": header})
    assert r.status_code == 401


# secrets.compare_digest refuses non-ASCII str outright (TypeError), so a
# non-ASCII password on either side has to be compared as UTF-8 bytes. The
# same reasoning as logic/bills/app.py's _require_admin.
def test_non_ascii_supplied_password_is_rejected_not_a_server_error():
    r = _app("s3cret").get("/private", headers=_auth("someone", "sénha"))
    assert r.status_code == 401


def test_non_ascii_configured_password_still_authenticates():
    # Otherwise a non-ASCII BILLS_APP_PASSWORD/APP_PASSWORD is a silent lockout.
    r = _app("sénha-forte").get("/private", headers=_auth("someone", "sénha-forte"))
    assert r.status_code == 200
