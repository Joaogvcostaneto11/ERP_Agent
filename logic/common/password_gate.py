from __future__ import annotations

import base64
import os
import secrets
from collections.abc import Iterable

from fastapi import FastAPI, Request, Response

_DEFAULT_EXEMPT = frozenset({"/healthz"})


# Render sets both of these on every service it runs. Either one means we are
# not on someone's laptop.
_DEPLOY_MARKERS = ("RENDER", "RENDER_SERVICE_ID")


def _is_deployed() -> bool:
    return any(os.environ.get(m) for m in _DEPLOY_MARKERS)


def install_password_gate(app: FastAPI, password: str | None, *, realm: str,
                          env_var: str,
                          exempt: Iterable[str] = _DEFAULT_EXEMPT) -> None:
    """Put a shared-password HTTP Basic gate in front of every path but `exempt`.

    Only the password half of the credential is checked and the username is
    ignored: the deployment shares one secret rather than issuing accounts.

    An unset password installs NO middleware at all, so local development and
    the test suite run ungated — but only off a deployed host. `env_var` names
    the variable to set and appears in the refusal below, so the error alone is
    enough to fix it.
    """
    if not password:
        if _is_deployed():
            # The secrets are typed into the Render dashboard by hand
            # (`sync: false`), so "forgot to fill it in" is one blank field
            # away from publishing an ungated service — and two of the three
            # write to the ERP database. Refuse to boot instead: a failed
            # deploy is loud, an ungated one is silent.
            raise RuntimeError(
                f"{realm}: {env_var} is not set, but this is a deployed "
                f"environment ({' or '.join(_DEPLOY_MARKERS)} is present). "
                f"Refusing to start without a password gate. Set {env_var} "
                "in the service's environment."
            )
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
    # Compare UTF-8 bytes rather than str: compare_digest rejects non-ASCII str
    # outright, which would turn a non-ASCII supplied password into a 500 and a
    # non-ASCII *configured* one into a silent permanent lockout. Same reasoning
    # as logic/bills/app.py's _require_admin.
    return secrets.compare_digest(supplied.encode("utf-8"), password.encode("utf-8"))
