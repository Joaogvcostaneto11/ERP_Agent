from __future__ import annotations

from fastapi import Request


def secure_cookie(request: Request) -> bool:
    """Whether this request's Set-Cookie should carry the Secure flag.

    Derived from the request rather than configured, so there is no third
    environment variable to forget: local dev over http keeps working, and a
    deployment behind TLS always marks its cookies Secure.

    Render (and every other reverse proxy) terminates TLS and forwards the
    original scheme in X-Forwarded-Proto, so the app itself sees a plain http
    request and that header is the only thing that says otherwise. A chain of
    proxies appends to the list, and the client-facing scheme is the first
    entry. Spoofing the header only affects the spoofer's own cookie; it
    cannot downgrade anyone else's connection.
    """
    forwarded = request.headers.get("x-forwarded-proto", "")
    if forwarded:
        return forwarded.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"
