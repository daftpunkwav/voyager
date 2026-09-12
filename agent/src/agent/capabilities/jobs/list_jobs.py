"""list_jobs capability: background tasks as the model/human sees them
(read-only projection over task.* events)."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="list_jobs",
        description="Background tasks (imports/indices/queues): id, kind, status, recency; source for the activity view",
    )
    def list_jobs(limit: int = 20) -> list[dict]:
        return deps.jobs.list_jobs(limit=max(1, min(int(limit), 100)))
