"""Composition root for the graph service.

Single wiring source for both standalone (rest.py) and aggregated
(packages/host/) runs. The scheduler is created by this service by default;
tests or a parent composition root may inject a custom one.

``call_sync`` is the composition root's synchronous late-bound call; graph
never imports the sources package. The type is SyncCall (domain, name, args).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .capabilities import Deps, init_deps, registry
from .engines.adapter import EngineAdapter
from .index_queue import IndexQueue
from .pipelines.code.analyze import analyze_repo
from .pipelines.l0 import relate as l0_relate
from .scheduler import IndexScheduler
from .settings import DEFAULT_C_URL, DEFS
from .store import GraphStore


def wire(
    data_dir: str | Path,
    *,
    bus: EventBus | None = None,
    c_url: str = DEFAULT_C_URL,
    engine_mode: str = "auto",
    scheduler: IndexScheduler | None = None,
    settings_store: SettingsStore | None = None,
    call_sync: l0_relate.SyncCall | None = None,
    workspace: str | Path | None = None,
) -> Wiring:
    """``call_sync`` is the composition root's synchronous late-bound call
    ``call(domain, name, args)``; graph consumes it as its L0 resource catalog
    provider (injected via ``needs`` in the module card)."""
    data_dir = Path(data_dir)
    workspace_root = (
        Path(workspace) if workspace else Path(__file__).resolve().parents[4] / "data" / "workspace"
    )
    if settings_store is not None:
        settings_store.register_fresh(DEFS)
    store = GraphStore(data_dir / "graph.db")
    queue = IndexQueue(data_dir / "index.db")
    adapter = EngineAdapter(
        c_base_url=c_url, python_data_root=data_dir / "engine-python", bus=bus, mode=engine_mode
    )
    init_deps(
        Deps(
            store=store,
            queue=queue,
            adapter=adapter,
            bus=bus,
            call_sync=call_sync,
            workspace=workspace_root,
        )
    )

    async def _run_job(job: dict) -> None:
        # Dispatch by job level (L0/L1 layering): l1 = deep single-resource
        # analysis (code engine); l0 = cross-resource relations (metadata
        # fallback; AI semantic relations are layered on by the agent via
        # the write primitives).
        if job.get("level") == "l0":
            kinds = job.get("kinds") or []
            await asyncio.to_thread(l0_relate.run_l0, store, call_sync, kinds=kinds)
            return
        await analyze_repo(adapter, store, project=job["project"], repo_path=job["repo_path"])

    sched = scheduler or IndexScheduler(queue, _run_job, bus)

    def probe() -> dict:
        return {"status": "up", "engine_mode": engine_mode}

    def close() -> None:
        store.close()
        queue.close()

    return Wiring(
        registry=registry,
        probe=probe,
        start=sched.start,
        stop=sched.stop,
        close=close,
    )
