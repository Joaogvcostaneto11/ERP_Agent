from __future__ import annotations

import base64
import secrets
from collections.abc import Iterable

from fastapi import FastAPI, Request, Response

_DEFAULT_EXEMPT = frozenset({"/healthz"})


def install_password_gate(app: FastAPI, password: str | None, *, realm: str,
                          exempt: Iterable[str] = _DEFAULT_EXEMPT) -> None:
    """Put a shared-password HTTP Basic gate in front of every path but `exempt`.

    Only the password half of the credential is checked and the username is
    ignored: the deployment shares one secret rather than issuing accounts.

    An unset password installs NO middleware at all, so local development and
    the test suite run ungated while the deployed services set the env var."""
    if not password:
        return
    exempt_paths = frozenset(exempt)

    @app.middleware("http")
    async def _basic_auth(request: Request, call_next):
        if request.url.path in exempt_paths or _authorized(
                request.headers.get("Authorization", ""), password):
            return await call_next(request)
        return Response(status_code=401,
                        headers={"WWW-Authenticate": f'Basic realm="{realm}"'})


def _authorized(header: str, password: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        _, _, supplied = base64.b64decode(header[6:]).decode("utf-8").partition(":")
    except Exception:
        return False  # malformed base64 or non-UTF-8 is simply not authorized
    return secrets.compare_digest(supplied, password)
