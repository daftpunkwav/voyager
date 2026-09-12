"""Background-job cancellation router: map a projected job to its source
domain's own cancel capability and execute it through the late-bound call.

The map lives in the composition root because it names domain capabilities
(the agent must not learn domain implementations); a domain without a
registered cancel capability yields an actionable error instead of a guess.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from platform_contracts import ErrorSuffix, ServiceError

log = logging.getLogger("host.jobs_router")

#: domain -> cancel capability name (+ the argument it takes). Extend when a
#: domain grows a long-running job kind.
_CANCEL_CAPABILITIES: dict[str, tuple[str, str]] = {
    "graph": ("cancel_index", "job_id"),
}

LateBoundCall = Callable[[str, str, dict[str, Any]], Awaitable[Any]]


def make_job_cancel_router(call: LateBoundCall, jobs_view: Any) -> Callable[[str], Any]:
    async def router(job_id: str) -> dict:
        job = jobs_view.find(job_id)
        if job is None:
            raise ServiceError("agent", ErrorSuffix.NOT_FOUND, f"no such background job: {job_id}")
        entry = _CANCEL_CAPABILITIES.get(job.get("source") or "")
        if entry is None:
            raise ServiceError(
                "agent",
                ErrorSuffix.UNAVAILABLE,
                f"domain {job.get('source')!r} exposes no cancel capability",
                hint="stop it from its domain page, or extend the host job router",
            )
        cap, arg = entry
        return await call(job["source"], cap, {arg: job_id})

    return router


__all__ = ["make_job_cancel_router"]
