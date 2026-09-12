"""Service assembly: the single wiring source for standalone mode
(rest.py) and aggregate deployment.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus

from .capabilities import Deps, init_deps, registry
from .store import JobStore
from .worker import Worker


def wire(data_dir: str | Path, *, bus: EventBus | None = None) -> Wiring:
    store = JobStore(Path(data_dir) / "template.db")
    queue: asyncio.Queue = asyncio.Queue()
    worker = Worker(store, bus, queue)
    init_deps(Deps(store=store, bus=bus, queue=queue))
    return Wiring(
        registry=registry,
        probe=lambda: {"status": "up"},
        start=worker.start,
        stop=worker.stop,
        close=store.close,
    )
