"""REST entry point for the llm service.

Run standalone: uvicorn llm.rest:app_factory --factory --port 8070
(from the repo root). All assembly lives in wiring.py; this file is only a
thin HTTP shell.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from platform_capability import build_router
from platform_contracts import HealthReport, HealthStatus

from .wiring import wire

_DEFAULT_DATA = Path(__file__).parents[2] / "data"  # package root: packages/<domain>/data


def create_app(data_dir: str | Path = _DEFAULT_DATA) -> FastAPI:
    w = wire(data_dir)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if w.close:
            w.close()

    app = FastAPI(title="llm", lifespan=lifespan)
    app.include_router(build_router(w.registry))

    @app.get("/health")
    async def health() -> dict:
        return HealthReport(service="llm", status=HealthStatus.UP).to_dict()

    return app


def app_factory() -> FastAPI:
    return create_app()
