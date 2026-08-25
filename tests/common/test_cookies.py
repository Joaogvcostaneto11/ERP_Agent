from __future__ import annotations

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from logic.common.cookies import secure_cookie


def _app():
    app = FastAPI()

    @app.get("/c")
    def c(request: Request, response: Response):
        response.set_cookie("k", "v", secure=secure_cookie(request))
        return {"ok": True}

    return app


def _set_cookie(base_url: str, headers: dict | None = None) -> str:
    with TestClient(_app(), base_url=base_url) as client:
        return client.get("/c", headers=headers or {}).headers["set-cookie"]


def test_plain_http_gets_no_secure_flag():
    # Local dev is served over http://localhost; a Secure cookie there is not
    # reliably stored by every browser, so it must stay off.
    assert "Secure" not in _set_cookie("http://testserver")


def test_direct_https_gets_the_secure_flag():
    assert "Secure" in _set_cookie("https://testserver")


def test_forwarded_https_gets_the_secure_flag():
    # Render terminates TLS and forwards the original scheme, so the app itself
    # sees a plain http request and only this header tells it otherwise.
    assert "Secure" in _set_cookie("http://testserver",
                                   {"X-Forwarded-Proto": "https"})


@pytest.mark.parametrize("value", ["https, http", "HTTPS"])
def test_forwarded_proto_variants_are_understood(value):
    # A chain of proxies appends to the list; the client-facing scheme is first.
    assert "Secure" in _set_cookie("http://testserver", {"X-Forwarded-Proto": value})


def test_forwarded_http_gets_no_secure_flag():
    assert "Secure" not in _set_cookie("http://testserver",
                                       {"X-Forwarded-Proto": "http"})
