"""Service mounting: attaches each service's registry-generated router
under /api/<domain>/.

The gateway never imports domain services itself — the mount list
(MountSpec) is assembled and injected by the deployment entry point
(composition root): in-memory registries in the monolith, HTTP reverse
proxy mounts in a microservice deployment, with the gateway code
unchanged. extra_router lets a domain bring its own routes (e.g.
read-only file downloads) served under the same /api/<domain> prefix —
the gateway still holds zero business logic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI
from platform_capability import Registry, build_router

from .health import HealthProbe, ProbeFn


@dataclass(frozen=True)
class MountSpec:
    """Mount description for one downstream service."""

    domain: str  # URL segment: /api/<domain>/capabilities/...
    registry: Registry  # the service's capability registry (in-process)
    probe: ProbeFn | None = None  # health probe fn (omit for passive only)
    extra_router: APIRouter | None = None  # domain-owned routes, same prefix


def mount_services(
    app: FastAPI,
    mounts: list[MountSpec],
    probe: HealthProbe,
    *,
    issuer=None,
    auth: list[Callable] | None = None,
    quota: list[Callable] | None = None,
    audit: list | None = None,
) -> None:
    """Mount all services: REST prefix /api/<domain>, probe registration,
    and per-route auth / quota / audit shared across routers."""
    for spec in mounts:
        router = build_router(
            spec.registry,
            issuer=issuer,
            auth=auth,
            quota=quota,
            audit=audit,
        )
        app.include_router(router, prefix=f"/api/{spec.domain}")
        if spec.extra_router is not None:
            app.include_router(spec.extra_router, prefix=f"/api/{spec.domain}")
        if spec.probe is not None:
            probe.register(spec.domain, spec.probe)
