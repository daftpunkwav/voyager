"""REST entry point for the notes service.

Run standalone from the repository root:
uvicorn notes.rest:app_factory --factory --port 8020.
All wiring lives in wiring.py; this file is only a thin HTTP shell.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from platform_capability import build_router
from platform_contracts import HealthReport, HealthStatus
from platform_eventbus import EventBus

from .assets import build_assets_router
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

    app = FastAPI(title="notes", lifespan=lifespan)
    app.include_router(build_router(w.registry))
    # Read-only asset routes; matches the aggregated form (gateway extra_router
    # uses the same prefix) -> /api/notes/assets/...
    app.include_router(build_assets_router(), prefix="/api/notes")

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="notes", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
