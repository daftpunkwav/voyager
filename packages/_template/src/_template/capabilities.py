"""Capability registry (single source of truth).

Responsibilities:
- Declare this service's capabilities on the module-level registry
- Hold the Deps dataclass and init_deps() for runtime dependency injection
- Keep handlers to business logic only (auth / rate limiting / auditing are
  framework entry-point concerns)

Pattern: a module-level registry plus init_deps() to inject runtime
dependencies (store / bus / queue). Handlers contain business logic
only; auth / rate limiting / auditing are enforced by the framework
entry points.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from platform_capability import Registry, capability
from platform_contracts import JobRef
from platform_eventbus import EventBus

from .store import JobStore

registry = Registry("template")


@dataclass
class Deps:
    """Service runtime dependencies, injected by the entry points
    (rest.py / mcp_server.py)."""

    store: JobStore
    bus: EventBus | None
    queue: asyncio.Queue  # long-running job queue: job_id


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps not injected: call init_deps() at service entry first")
    return _deps


@dataclass
class EchoIn:
    text: str
    shout: bool = False


@capability(
    registry, name="echo", description="Echo text; uppercased when shout=true", input_model=EchoIn
)
def echo(data: EchoIn) -> dict:
    return {"echo": data.text.upper() if data.shout else data.text}


@capability(
    registry,
    name="get_info",
    description="Service self-check: name/protocol version/pending task count",
)
def get_info() -> dict:
    deps = _require_deps()
    return {
        "service": "template",
        "protocol": "0.1.0",
        "pending_jobs": deps.queue.qsize(),
    }


@capability(
    registry,
    name="submit_job",
    description="Submit a sample long-running task; returns job_id immediately, progress via task.progress/completed events",
    long_running=True,
)
def submit_job() -> JobRef:
    """Long-running job convention: enqueue only, never block; worker.py
    performs execution and emits progress events."""
    deps = _require_deps()
    job_id = uuid.uuid4().hex[:12]
    deps.store.enqueue(job_id)
    deps.queue.put_nowait(job_id)
    return JobRef(job_id=job_id)
