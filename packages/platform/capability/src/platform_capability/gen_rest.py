"""Registry to FastAPI router (one of the two generated protocols).

fastapi is an optional dependency (extra `rest`) imported only when
build_router is called. Conventions: GET {prefix} lists capabilities;
POST {prefix}/{name} invokes one with a JSON object; JobRef maps to
202 Accepted; ServiceError maps to the unified error body plus HTTP status.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from typing import Any

from platform_actor import ActorContext, LocalTokenIssuer, resolve_http_actor
from platform_contracts import ErrorSuffix, JobRef, ServiceError

from platform_capability.guards import AuditSink, CallRequest, execute
from platform_capability.registry import Registry

#: Aggregate request-body cap for the generated JSON routes: the body is read
#: fully into memory before the guard chain runs and JSON has no natural size
#: bound (file uploads ride the multipart transport, not this router). 10MB
#: is far above any legitimate structured call. Oversize is a 400-class
#: INVALID_INPUT rejection: the ErrorSuffix vocabulary is synced with the web
#: client (errorCodes.ts + locales), so no dedicated 413 suffix is added for
#: a loopback-bound transport bound.
_MAX_BODY_BYTES = 10 * 1024 * 1024


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
    quota: list[Callable[[CallRequest], None]] | None = None,
    audit: list[AuditSink | Callable] | None = None,
    prefix: str = "/capabilities",
    max_body_bytes: int = _MAX_BODY_BYTES,
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

    def _too_large() -> ServiceError:
        return ServiceError(
            registry.domain,
            ErrorSuffix.INVALID_INPUT,
            f"request body exceeds the {max_body_bytes}-byte transport cap",
            hint="send a smaller payload; file uploads go through the multipart transport",
        )

    @router.get(prefix)
    async def list_capabilities() -> dict[str, Any]:
        return {"capabilities": [_spec(c) for c in registry.all()]}

    @router.post(prefix + "/{name}")
    async def call_capability(name: str, request: Request):
        """Invoke one capability with a JSON object body.

        Success envelope: {"result": <return value>} — dataclass returns are
        flattened to dicts, and a long_running capability answers
        202 {"job": {...}} instead. Output shapes have no schema
        registration face (inputs only, see capability_input_schema), so
        consumers normalize per capability (e.g. the web apps' api/ facades);
        a capability that changes its return shape owns updating those
        consumers. Failures use the ServiceError envelope with the mapped
        HTTP status."""
        try:
            try:
                # Read with a hard byte cap instead of request.json(): the
                # honest Content-Length pre-check rejects declared oversize
                # before a byte is read, and the chunked read keeps a lying
                # (small) header or a chunked body from filling memory
                # behind it.
                declared = request.headers.get("content-length")
                if declared is not None:
                    try:
                        if int(declared) > max_body_bytes:
                            raise _too_large()
                    except ValueError:
                        pass  # garbage header: fall through to the streamed cap
                raw = bytearray()
                async for chunk in request.stream():
                    raw.extend(chunk)
                    if len(raw) > max_body_bytes:
                        raise _too_large()
                body = json.loads(bytes(raw))
            except ServiceError:
                raise
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
            result = await execute(registry, name, ctx, body, quota=quota, audit=audit)
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
