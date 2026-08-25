from __future__ import annotations

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from logic.common.security_headers import install_security_headers

_CSP = "default-src 'self'"


def _client():
    app = FastAPI()

    @app.get("/p")
    def p():
        return {"ok": True}

    @app.get("/own-csp")
    def own_csp():
        return Response("<p>x</p>", media_type="text/html",
                        headers={"Content-Security-Policy": "default-src 'none'"})

    install_security_headers(app, csp=_CSP)
    return TestClient(app)


@pytest.mark.parametrize("header,value", [
    ("Content-Security-Policy", _CSP),
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "same-origin"),
    ("X-Frame-Options", "DENY"),
])
def test_baseline_headers_are_set(header, value):
    assert _client().get("/p").headers[header] == value


def test_a_route_with_a_stricter_policy_keeps_it():
    # The report view locks itself down harder than the app baseline; the
    # middleware must not relax it back.
    r = _client().get("/own-csp")
    assert r.headers["Content-Security-Policy"] == "default-src 'none'"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
