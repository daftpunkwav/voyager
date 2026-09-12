"""HTTP identity resolution via Bearer token or session cookie.

Invalid tokens fail closed; tokenless requests map to the local user only
when they originate from a loopback address.
"""

from __future__ import annotations

import ipaddress

from platform_contracts import LOCAL_USER, ActorRef, ErrorSuffix, ServiceError

from platform_actor.token import LocalTokenIssuer

COOKIE_NAME = "local_session"
_DOMAIN = "actor"

# Non-IP loopback aliases; the Starlette TestClient reports client host "testclient"
_LOOPBACK_NAMES = frozenset({"localhost", "testclient"})
_PUBLIC_PATHS = frozenset({"/health", "/api/session/bootstrap"})


def is_loopback(request) -> bool:
    """Whether the request originates from loopback.

    Covers the Starlette TestClient and IPv4-mapped ::ffff:127.0.0.1 addresses.
    """
    client = getattr(request, "client", None)
    host = (client.host if client is not None else "") or ""
    if host in _LOOPBACK_NAMES:
        return True
    try:
        addr = ipaddress.ip_address(host)
        mapped = getattr(addr, "ipv4_mapped", None)
        return (mapped or addr).is_loopback
    except ValueError:
        return False


def is_public_path(path: str) -> bool:
    """Token-free health/bootstrap endpoints."""
    return path in _PUBLIC_PATHS


def token_from_request(request) -> str | None:
    """Prefer the Authorization: Bearer header, then the HttpOnly cookie."""
    header = request.headers.get("authorization") or ""
    if header.startswith("Bearer "):
        token = header.removeprefix("Bearer ").strip()
        if token:
            return token
    cookies = getattr(request, "cookies", None)
    if cookies is not None:
        cookie = cookies.get(COOKIE_NAME)
        if cookie:
            return cookie
    return None


def resolve_http_actor(request, issuer: LocalTokenIssuer | None) -> ActorRef:
    """Resolve the caller.

    Without an issuer, single-user local semantics apply; with one, requests
    from non-loopback addresses must present a valid token.
    """
    if issuer is None:
        return LOCAL_USER
    token = token_from_request(request)
    if token:
        return issuer.verify(token)
    if is_loopback(request):
        return LOCAL_USER
    raise ServiceError(
        _DOMAIN,
        ErrorSuffix.AUTH_REQUIRED,
        "local session token required",
        hint="open the app from a loopback address to issue a session, or send Authorization: Bearer",
    )
