"""cancel_run capability: emergency-stop a running subagent by id or name
("chat" = the chat main instance).

`cancel_run()` is the one implementation; the capability and the agent's
cancel_run tool both bind it. Both the user and the agent may cancel.
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.subagent.spawn import Spawner


async def cancel_run(spawner: Spawner, id_or_name: str) -> dict:
    cancelled = await spawner.cancel(id_or_name)
    if not cancelled:
        raise ServiceError(
            "agent",
            ErrorSuffix.NOT_FOUND,
            f"no matching running instance: {id_or_name}",
            hint="see list_subagents for running instances",
        )
    return {"cancelled": cancelled}


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="cancel_run",
        description="Emergency-stop a running subagent (by id or name; 'chat' = the chat main instance)",
        cost=1,
    )
    async def _cancel_run(id_or_name: str) -> dict:
        return await cancel_run(deps.spawner, id_or_name)
