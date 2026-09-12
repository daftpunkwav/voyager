"""cancel_job capability: cancel one background task by routing to its
source domain's own cancel capability (the router is injected by the
composition root; this module never learns domain implementations)."""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def cancel_job(deps: CapabilityDeps, job_id: str) -> dict:
    """Shared implementation (the agent tool of the same name binds this)."""
    if deps.job_cancel is None:
        raise ServiceError(
            "agent",
            ErrorSuffix.UNAVAILABLE,
            "no cancellation router wired for background jobs",
        )
    return deps.job_cancel(job_id)


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="cancel_job",
        description="Cancel a background task (routes to the source domain's own cancel capability)",
        cost=1,
    )
    async def _cancel_job(job_id: str) -> dict:
        return cancel_job(deps, job_id)
