"""Jobs capability group (background-task projection + cancellation).
Zero-logic aggregation: import each capability file and register it."""

from __future__ import annotations

from platform_capability import Registry

from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.jobs.cancel_job import register as _cancel_job
from agent.capabilities.jobs.list_jobs import register as _list_jobs


def register(reg: Registry, deps: CapabilityDeps) -> None:
    _list_jobs(reg, deps)
    _cancel_job(reg, deps)
