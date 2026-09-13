"""wait_subagent capability: block until a dispatched subagent reaches a
terminal state (or the timeout), then return its status and full result.

The one implementation; the capability and the agent's wait_subagent tool
both bind it. Use after spawn_subagent when the next action depends on the
result - prefer the completion notice for fire-and-forget work.
"""

from __future__ import annotations

import asyncio

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.runtime.state import RunStatus
from agent.subagent.spawn import Spawner

#: Poll interval while waiting for the instance to reach a terminal state
_POLL_S = 0.5

#: Default and maximum wait (seconds); waiting is synchronous by design, so
#: the default stays modest and the cap bounds how long a turn can stall
DEFAULT_TIMEOUT_S = 120.0
MAX_TIMEOUT_S = 600.0

_TERMINAL = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED})


def _find(spawner: Spawner, id_or_name: str):
    for inst in spawner.instances.values():
        if id_or_name in (inst.id, inst.name):
            return inst
    return None


async def wait_subagent(
    spawner: Spawner, id_or_name: str, timeout_s: float = DEFAULT_TIMEOUT_S
) -> dict:
    """Wait for one instance to finish; raises NOT_FOUND when nothing matches
    (deferred tasks are not yet spawned - see list_subagents)."""
    try:
        timeout = min(max(float(timeout_s), 0.1), MAX_TIMEOUT_S)
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_S
    inst = _find(spawner, id_or_name)
    if inst is None:
        raise ServiceError(
            "agent",
            ErrorSuffix.NOT_FOUND,
            f"no matching instance: {id_or_name}",
            hint="see list_subagents for running instances",
        )
    deadline = asyncio.get_running_loop().time() + timeout
    while inst.status not in _TERMINAL and inst.status is not RunStatus.PAUSED:
        if asyncio.get_running_loop().time() >= deadline:
            return {
                "id": inst.id,
                "name": inst.name,
                "status": inst.status.value,
                "timed_out": True,
                "last_step": inst.last_step_summary(),
            }
        await asyncio.sleep(_POLL_S)
    return {
        "id": inst.id,
        "name": inst.name,
        "status": inst.status.value,
        "timed_out": False,
        "result": str(inst.state.result or ""),
        "error": str(inst.state.error or ""),
    }


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="wait_subagent",
        description=(
            "Wait for a dispatched subagent (by id or name) to finish and return"
            " its status plus the full result; use when the next action depends"
            " on the outcome"
        ),
        cost=1,
    )
    async def _wait_subagent(id_or_name: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> dict:
        return await wait_subagent(deps.spawner, id_or_name, timeout_s)
