"""Gateway service assembly: the single aggregate entry point for humans.

Run standalone with:
  uvicorn gateway.rest:app_factory --factory --port 8000
(standalone mode = empty mounts, only session/chat/activity/health; the mount
list and lifespan are injected by the deployment entry point via
create_app).

Error convention: ServiceError -> unified error envelope via a global
exception handler. Errors inside capability routes are already mapped by
build_router; this handler covers the gateway's own endpoints
(chat/activity etc.) and unexpected exceptions.
"""

from __future__ import annotations

import ipaddress
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from platform_actor import is_public_path, resolve_http_actor
from platform_contracts import (
    LOCAL_USER,
    HealthReport,
    HealthStatus,
    ServiceError,
)
from platform_eventbus import EventBus, EventLog

from .activity import build_activity_router
from .chat import build_chat_router
from .health import HealthProbe
from .mounts import MountSpec, mount_services
from .ratelimit import RateLimiter
from .session import build_session_router

_DEFAULT_DB = Path(__file__).parents[2] / "data" / "events.db"  # package root

#: Loopback-ish Host/Origin names always trusted: the real loopback family
#: plus the ASGI test-client virtual-host names (the TestClient reports Host
#: "testserver", matching the "testclient" remote-host allowance in
#: platform_actor.http_auth).
_TRUSTED_HOST_NAMES = frozenset({"localhost", "testclient", "testserver"})


def _trusted_host(value: str) -> bool:
    """Whether a Host header / origin hostname names this machine.

    Accepts IP literals in loopback/private space (127.x, RFC1918, ::1 —
    the deployment is loopback-bound, but a LAN-IP host header with a Bearer
    token keeps working) and the localhost family; any other DNS name is
    rejected. That name rejection is the DNS-rebinding defense: a rebound
    attacker domain resolves to 127.0.0.1 but still presents its own name in
    Host, so every request it carries fails here.
    """
    host = (value or "").strip()
    if not host:
        return False
    if host.startswith("["):  # [::1] or [::1]:8000
        host = host[1:].split("]", 1)[0]
    elif host.count(":") == 1:  # name-or-IPv4:port (a bare IPv6 never has one colon)
        host = host.rsplit(":", 1)[0]
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        h = host.lower().rstrip(".")
        return h in _TRUSTED_HOST_NAMES or h.endswith(".localhost")
    mapped = getattr(addr, "ipv4_mapped", None)
    return (mapped or addr).is_private or addr.is_loopback or addr.is_unspecified


def _trusted_origin(value: str) -> bool:
    """Whether an Origin header belongs to the app's own loopback surface.

    Browsers attach Origin to every cross-site request (and to same-site
    non-GET ones), so requiring a loopback origin stops cross-origin CSRF
    against the write endpoints (chat/messages, uploads, workspace switch)
    from any web page the user visits. The port is not compared: the vite
    dev server on :5173 proxies to the API with its own origin attached.
    """
    parsed = urlparse((value or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    return _trusted_host(parsed.hostname)


def create_app(
    mounts: list[MountSpec] | None = None,
    *,
    db_path: str | Path = _DEFAULT_DB,
    bus: EventBus | None = None,
    lifespan=None,
    issuer=None,
    auth: list | None = None,
    quota: list | None = None,
    audit: list | None = None,
    rate_limit_per_minute: int = 600,
    sse_max_connections: int = 8,
    history_page_size: int = 200,
    trajectory_page_size: int = 500,
    extra_routers: list | None = None,
    trajectory=None,  # chat.TrajectoryReader: projection-backed /api/chat/trajectory
    uploads_workspace: Path | None = None,  # mount /api/uploads with the shared limiter
) -> FastAPI:
    if bus is None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        bus = EventBus(EventLog(db_path))
    limiter = RateLimiter(rate_limit_per_minute, sse_max_connections)
    probe = HealthProbe(bus)

    if lifespan is None:

        @asynccontextmanager
        async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
            yield

    app = FastAPI(title="gateway", lifespan=lifespan)

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        # Mirrors the index.html meta CSP: 'unsafe-eval' + blob: are required
        # by the fenced-code runner (skulpt eval; js/ts snippets in a blob
        # worker). Injection stays guarded by the markdown sanitize allowlist.
        response.headers.setdefault(
            "Content-Security-Policy",
            "frame-ancestors 'none'; default-src 'self'; "
            "script-src 'self' 'unsafe-eval' blob:; worker-src 'self' blob:",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    @app.exception_handler(ServiceError)
    async def _service_error(_req: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        # Malformed query/path parameters must land in the same envelope as
        # every other client error; the FastAPI default leaks a bare
        # {"detail": [...]} that clients cannot branch on.
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", ()) if p != "query")
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "code": "GATEWAY.INVALID_INPUT",
                    "message": f"invalid parameter '{loc}': {first.get('msg', 'validation failed')}",
                }
            },
        )

    @app.middleware("http")
    async def _actor_middleware(request: Request, call_next):
        # Identity resolution: a valid Bearer/Cookie maps to its actor (failure
        # -> 401, never a silent downgrade); without a token only loopback is
        # treated as the local single user; non-loopback without a token -> 401.
        # Health checks and bootstrap paths are allowed through.
        if is_public_path(request.url.path):
            request.state.actor = LOCAL_USER
            return await call_next(request)
        try:
            request.state.actor = resolve_http_actor(request, issuer)
        except ServiceError as exc:
            return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())
        return await call_next(request)

    @app.middleware("http")
    async def _origin_guard(request: Request, call_next):
        # Local REST surface gate (defined last = outermost middleware, so it
        # runs before identity resolution): Host must name this machine
        # (DNS-rebinding defense — a rebound attacker domain resolves to
        # 127.0.0.1 but still carries its own name in Host), and a browser-
        # attached Origin must be the app's own loopback origin (CSRF defense
        # — browsers always attach Origin to cross-site requests, so a web
        # page the user visits cannot drive the write endpoints; non-browser
        # clients send no Origin and are unaffected).
        if not _trusted_host(request.headers.get("host", "")):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "GATEWAY.FORBIDDEN",
                        "message": "request host is not trusted (DNS rebinding protection)",
                    }
                },
            )
        origin = request.headers.get("origin")
        if origin and not _trusted_origin(origin):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "GATEWAY.FORBIDDEN",
                        "message": "cross-origin request rejected (CSRF protection)",
                    }
                },
            )
        return await call_next(request)

    mount_services(app, mounts or [], probe, issuer=issuer, auth=auth, quota=quota, audit=audit)
    app.include_router(build_session_router(issuer))
    # Cross-cutting routers injected by the deployment entry point (e.g. file
    # upload endpoints); the gateway holds no domain business logic, only
    # cross-cutting concerns (actor auth, rate limiting, security headers,
    # health aggregation)
    for router in extra_routers or []:
        app.include_router(router)
    app.include_router(
        build_chat_router(
            bus,
            limiter,
            history_page_size=history_page_size,
            trajectory_page_size=trajectory_page_size,
            trajectory=trajectory,
        )
    )
    app.include_router(build_activity_router(bus, limiter))
    # Shared limiter on app.state: the workspace hot-swap path (agent_rebuild)
    # re-mounts /api/uploads outside create_app and needs the same limiter.
    app.state.limiter = limiter
    if uploads_workspace is not None:
        from .uploads import build_upload_router

        app.include_router(build_upload_router(uploads_workspace, limiter))

    @app.get("/health")
    async def health() -> dict:
        await probe.probe_all()
        return {
            **HealthReport(service="gateway", status=HealthStatus(probe.overall())).to_dict(),
            "services": probe.snapshot(),
        }

    return app


def app_factory() -> FastAPI:
    return create_app()
