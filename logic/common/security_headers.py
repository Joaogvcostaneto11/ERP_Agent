from __future__ import annotations

from fastapi import FastAPI

# Set on every response unless the route already said something stricter.
_BASELINE = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    # None of the three UIs is ever framed, and `frame-ancestors` in the CSP
    # says the same thing to newer browsers. Both, because they are read by
    # different generations of browser.
    "X-Frame-Options": "DENY",
}


def install_security_headers(app: FastAPI, *, csp: str) -> None:
    """Attach the baseline response headers, with a per-app CSP.

    The CSP differs per service because only the chat UI loads scripts from a
    CDN, so it is passed in rather than fixed here.

    Every header is applied with setdefault: a route that has already set a
    stricter value of its own keeps it. /report/{id}/view depends on that — it
    serves model-authored HTML and denies far more than the app baseline does.
    """

    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", csp)
        for header, value in _BASELINE.items():
            response.headers.setdefault(header, value)
        return response
