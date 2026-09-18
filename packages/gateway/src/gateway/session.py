"""Local session bootstrap: loopback GET sets an HttpOnly cookie so the
browser carries credentials on subsequent requests.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from platform_actor import COOKIE_NAME, LocalTokenIssuer, is_loopback
from platform_contracts import LOCAL_USER, ErrorSuffix, ServiceError

_TTL = 30 * 24 * 3600


def build_session_router(issuer: LocalTokenIssuer | None) -> APIRouter:
    router = APIRouter()

    @router.get("/api/session/bootstrap")
    async def bootstrap(request: Request) -> JSONResponse:
        if issuer is None:
            return JSONResponse({"ok": True, "mode": "open"})
        if not is_loopback(request):
            raise ServiceError(
                "actor",
                ErrorSuffix.FORBIDDEN,
                "session issuing is only allowed from loopback",
                hint="access this app via 127.0.0.1",
            )
        token = issuer.issue(LOCAL_USER, ttl_seconds=_TTL)
        resp = JSONResponse({"ok": True, "mode": "cookie"})
        resp.set_cookie(
            COOKIE_NAME,
            token,
            httponly=True,
            samesite="lax",
            # secure stays off deliberately: this app serves plain http on
            # loopback (single-user local deployment), and browsers refuse
            # to send Secure cookies over http. Non-loopback access needs a
            # Bearer token instead (no cookie is issued there).
            secure=False,
            max_age=_TTL,
            path="/",
        )
        return resp

    return router
