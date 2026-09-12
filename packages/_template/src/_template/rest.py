"""Registry -> FastAPI app (standalone service entry point, run
from the repo root).

Run with: uvicorn _template.rest:app_factory --factory --port 8090,
or mount through the gateway. Importing this module has no side effects
(no database creation, no worker startup); all assembly lives in
wiring.py and this file is a thin HTTP shell.
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


def create_app(data_dir: str | Path = _DEFAULT_DATA, bus: EventBus | None = None) -> FastAPI:
    w = wire(data_dir, bus=bus)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if w.start:
            await w.start()
        yield
        if w.stop:
            await w.stop()
        if w.close:
            w.close()

    app = FastAPI(title="template", lifespan=lifespan)
    app.include_router(build_router(w.registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="template", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
