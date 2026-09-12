"""REST entry point for the graph service.

Run standalone with:
uvicorn graph.rest:app_factory --factory --port 8030 (from repo root).
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

from .scheduler import IndexScheduler
from .settings import DEFAULT_C_URL
from .wiring import wire

_DEFAULT_DATA = Path(__file__).parents[2] / "data"  # package root: packages/<domain>/data


def create_app(
    data_dir: str | Path = _DEFAULT_DATA,
    bus: EventBus | None = None,
    *,
    c_url: str = DEFAULT_C_URL,
    engine_mode: str = "auto",
    scheduler: IndexScheduler | None = None,
) -> FastAPI:
    w = wire(data_dir, bus=bus, c_url=c_url, engine_mode=engine_mode, scheduler=scheduler)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if w.start:
            await w.start()
        yield
        if w.stop:
            await w.stop()
        if w.close:
            w.close()

    app = FastAPI(title="graph", lifespan=lifespan)
    app.include_router(build_router(w.registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="graph", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
