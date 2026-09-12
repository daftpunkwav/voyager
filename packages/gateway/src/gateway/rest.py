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

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
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
        response.headers.setdefault(
            "Content-Security-Policy",
            "frame-ancestors 'none'; default-src 'self'",
        )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response

    @app.exception_handler(ServiceError)
    async def _service_error(_req: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())

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
