"""REST entry point for the office service.

Run standalone from the repository root with:
uvicorn office.rest:app_factory --factory --port 8040.
All wiring lives in wiring.py; this module is only a thin HTTP shell.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from platform_capability import build_router
from platform_contracts import HealthReport, HealthStatus
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .wiring import wire

_DEFAULT_DATA = Path(__file__).parents[2] / "data"  # package root: packages/<domain>/data


def create_app(
    data_dir: str | Path = _DEFAULT_DATA,
    bus: EventBus | None = None,
    settings_store: SettingsStore | None = None,
) -> FastAPI:
    w = wire(data_dir, bus=bus, settings_store=settings_store)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if w.close:
            w.close()

    app = FastAPI(title="office", lifespan=lifespan)
    app.include_router(build_router(w.registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="office", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
