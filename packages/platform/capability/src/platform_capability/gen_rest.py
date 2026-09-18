"""Registry to FastAPI router (one of the two generated protocols).

fastapi is an optional dependency (extra `rest`) imported only when
build_router is called. Conventions: GET {prefix} lists capabilities;
POST {prefix}/{name} invokes one with a JSON object; JobRef maps to
202 Accepted; ServiceError maps to the unified error body plus HTTP status.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any

from platform_actor import ActorContext, LocalTokenIssuer, resolve_http_actor
from platform_contracts import JobRef, ServiceError

from platform_capability.guards import AuditSink, CallRequest, execute
from platform_capability.registry import Registry


def _spec(cap) -> dict[str, Any]:
    from platform_capability.gen_mcp import capability_input_schema

    return {
        "name": cap.name,
        "description": cap.description,
        "cost": cap.cost,
        "reversible": cap.reversible,
        "scopes": sorted(cap.scopes),
        "long_running": cap.long_running,
        "streaming": cap.streaming,
        "input": capability_input_schema(cap),
    }


def build_router(
    registry: Registry,
    *,
    issuer: LocalTokenIssuer | None = None,
    auth: list[Callable[[CallRequest], None]] | None = None,
    quota: list[Callable[[CallRequest], None]] | None = None,
    audit: list[AuditSink | Callable] | None = None,
    prefix: str = "/capabilities",
):
    """Generate a FastAPI router from the registry. Raises RuntimeError when
    fastapi is not installed."""
    try:
        from fastapi import APIRouter, Request
        from fastapi.responses import JSONResponse
    except ImportError as exc:
        raise RuntimeError(
            "build_router requires fastapi: pip install 'platform-capability[rest]'"
        ) from exc

    # FastAPI resolves annotation strings against this module's namespace at
    # route registration (this module uses `from __future__ import
    # annotations`). The lazily imported Request must be injected into the
    # module namespace, otherwise the request parameter would be mistaken
    # for a query parameter (422).
    globals()["Request"] = Request

    router = APIRouter()

    @router.get(prefix)
    async def list_capabilities() -> dict[str, Any]:
        return {"capabilities": [_spec(c) for c in registry.all()]}

    @router.post(prefix + "/{name}")
    async def call_capability(name: str, request: Request):
        try:
            try:
                body = await request.json()
            except Exception as exc:  # unparseable body is a 400, not a silent {}
                from platform_contracts import ErrorSuffix

                raise ServiceError(
                    registry.domain, ErrorSuffix.INVALID_INPUT, "request body must be valid JSON"
                ) from exc
            if not isinstance(body, dict):
                from platform_contracts import ErrorSuffix

                raise ServiceError(
                    registry.domain, ErrorSuffix.INVALID_INPUT, "request body must be a JSON object"
                )
            if registry.get(name).streaming:
                # Streaming capabilities return AsyncIterator, which cannot be
                # JSON-serialized; reject explicitly rather than letting it
                # blow up as a 500 during response encoding.
                from platform_contracts import ErrorSuffix

                raise ServiceError(
                    registry.domain,
                    ErrorSuffix.UNAVAILABLE,
                    f"streaming capability {name} supports in-process consumption only; not available over REST",
                )
            ctx = _resolve_context(request, issuer)
            result = await execute(registry, name, ctx, body, auth=auth, quota=quota, audit=audit)
        except ServiceError as exc:
            return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())
        if isinstance(result, JobRef):
            return JSONResponse(status_code=202, content={"job": result.to_dict()})
        if dataclasses.is_dataclass(result) and not isinstance(result, type):
            result = dataclasses.asdict(result)
        return {"result": result}

    return router


def _resolve_context(request, issuer: LocalTokenIssuer | None) -> ActorContext:
    """Prefer the actor written by the aggregate entry's middleware; when
    mounted standalone, resolve Bearer/Cookie/loopback here."""
    actor = getattr(getattr(request, "state", None), "actor", None)
    if actor is not None:
        return ActorContext(actor=actor)
    return ActorContext(actor=resolve_http_actor(request, issuer))
