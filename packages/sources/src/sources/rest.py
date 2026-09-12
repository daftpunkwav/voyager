"""Aggregate REST entry point for sources.

Standalone run: uvicorn sources.rest:app_factory --factory
--port 8010 (repo root). All wiring lives in wiring.py; this file is a
thin HTTP shell that also mounts the read-only document-file router
handed over by wire (paths come from the DB by id, blocking traversal).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from platform_capability import build_router
from platform_contracts import HealthReport, HealthStatus
from platform_eventbus import EventBus

from .wiring import wire

_DEFAULT_DATA = Path(__file__).parents[2] / "data"  # package root: packages/<domain>/data
_DEFAULT_WORKSPACE = Path(__file__).parents[4] / "data" / "workspace"  # repo root


def create_app(
    data_dir: str | Path = _DEFAULT_DATA,
    workspace: str | Path = _DEFAULT_WORKSPACE,
    bus: EventBus | None = None,
) -> FastAPI:
    w = wire(data_dir, workspace=workspace, bus=bus)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if w.start:
            await w.start()
        yield
        if w.stop:
            await w.stop()
        if w.close:
            w.close()

    app = FastAPI(title="sources", lifespan=lifespan)
    app.include_router(build_router(w.registry))
    # Read-only document-file router handed over by wire (extra_router);
    # same prefix layout as the aggregate form (the gateway forwards it
    # verbatim): /api/sources/files/...
    if w.extra_router is not None:
        app.include_router(w.extra_router, prefix="/api/sources")

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="sources", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
