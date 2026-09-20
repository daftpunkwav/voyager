"""jobs capability: background tasks as the model/human sees them — one
action parameter covers list/reorder/cancel.

list is a read-only projection over task.* events (source for the activity
view); cancel and reorder route to the job's source domain capability through
routers injected by the composition root (this module never learns domain
implementations). The agent's jobs tool binds this same capability.
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


async def jobs_action(
    deps: CapabilityDeps, *, action: str, job_id: str = "", limit: int = 20, priority=None
) -> dict | list:
    if action == "list":
        return deps.jobs.list_jobs(limit=max(1, min(int(limit), 100)))
    if action == "reorder":
        if deps.job_reorder is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.UNAVAILABLE,
                "no reorder router wired for background jobs",
            )
        if priority is None:
            raise ServiceError(
                "agent", ErrorSuffix.INVALID_INPUT, "reorder needs a priority (lower runs first)"
            )
        return await deps.job_reorder(job_id, int(priority))
    if action == "cancel":
        if deps.job_cancel is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.UNAVAILABLE,
                "no cancellation router wired for background jobs",
            )
        return await deps.job_cancel(job_id)
    raise ServiceError(
        "agent",
        ErrorSuffix.INVALID_INPUT,
        f"unknown action: {action!r}",
        hint="valid actions: list/reorder/cancel",
    )


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="jobs",
        description=(
            "Background tasks: action list (limit; id/kind/status/recency projection), "
            "reorder (job_id,priority — lower value runs first), "
            "cancel (job_id; routes to the source domain's cancel capability)"
        ),
    )
    async def jobs(
        action: str, job_id: str = "", limit: int = 20, priority: int | None = None
    ) -> dict | list:
        return await jobs_action(deps, action=action, job_id=job_id, limit=limit, priority=priority)
