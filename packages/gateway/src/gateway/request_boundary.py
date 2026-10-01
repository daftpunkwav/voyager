"""Shared request-boundary helpers for the gateway's own routers.

One definition each for the contracts every gateway route repeats:
- actor resolution: the aggregate entry's middleware writes
  request.state.actor before any route runs (or rejects the request); the
  LOCAL_USER fallback only covers standalone deployments mounted without
  that middleware — never a downgrade on the aggregate surface.
- JSON body parsing: bad JSON / non-object -> 400 GATEWAY.INVALID_INPUT.
- session ids: the strict shape the agent store enforces, validated at
  every route that accepts the parameter, so the input contract does not
  vary by endpoint and a malformed id is a 400 instead of a stranded
  message or a silently empty filter.
"""

from __future__ import annotations

import re

from fastapi import Request
from platform_contracts import LOCAL_USER, ActorRef, ErrorSuffix, ServiceError

_DOMAIN = "gateway"

#: Session ids ride event payloads; the same strict shape the agent store
#: enforces.
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def actor_of(request: Request) -> ActorRef:
    """The request's resolved actor; LOCAL_USER when mounted standalone
    without the aggregate entry's actor middleware."""
    return getattr(request.state, "actor", None) or LOCAL_USER


async def json_body(request: Request) -> dict:
    """Parse and validate the request body: bad JSON / non-object -> 400, not 500."""
    try:
        body = await request.json()
    except Exception as exc:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.INVALID_INPUT, "Request body must be valid JSON"
        ) from exc
    if not isinstance(body, dict):
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, "Request body must be a JSON object")
    return body


def session_or_400(session: object) -> str:
    """Validate one `session` value (a body field or a query argument) and
    return it stripped; empty/absent stays empty (the default lane). A
    non-string value is invalid input (400), not a 500."""
    if session is None or session == "":
        return ""
    if not isinstance(session, str):
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "session must match [A-Za-z0-9_-]{1,64}",
        )
    sid = session.strip()
    if sid and not SESSION_ID_RE.match(sid):
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "session must match [A-Za-z0-9_-]{1,64}",
        )
    return sid
