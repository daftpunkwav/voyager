"""REST entry point for the code-exec service.

Run standalone: uvicorn code_exec.rest:app_factory --factory
--port 8050 (from the repo root). All assembly lives in wiring.py; this file
is only a thin HTTP shell.
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
    settings_store=None,
) -> FastAPI:
    w = wire(data_dir, workspace=workspace, bus=bus, settings_store=settings_store)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if w.close:
            w.close()

    app = FastAPI(title="code-exec", lifespan=lifespan)
    app.include_router(build_router(w.registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="code-exec", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
