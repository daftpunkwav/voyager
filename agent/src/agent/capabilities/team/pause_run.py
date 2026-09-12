"""pause_run capability: cooperatively pause a running instance at the next
step boundary (the agent-side counterpart of resume_run; phase 20).

`pause_run()` is the one implementation; the capability and the agent's
pause_run tool both bind it.
"""

from __future__ import annotations

from typing import Any

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.subagent.spawn import Spawner


def pause_run(spawner: Spawner, chat: Any, id_or_name: str) -> dict:
    """Resolve and flag one instance for cooperative pause; the turn machinery
    (turn.py) honors the flag at the next step boundary and emits AgentPaused."""
    if id_or_name == "chat":
        inst = chat
    else:
        inst = next(
            (i for i in spawner.instances.values() if i.id == id_or_name or i.name == id_or_name),
            None,
        )
    if inst is None:
        raise ServiceError(
            "agent",
            ErrorSuffix.NOT_FOUND,
            f"no matching instance: {id_or_name}",
            hint="see list_subagents for running instances",
        )
    if inst.status.value in ("completed", "failed", "cancelled"):
        # Pending/running/waiting_input instances can all take a pause flag
        raise ServiceError(
            "agent",
            ErrorSuffix.CONFLICT,
            f"instance {inst.name} is {inst.status.value}, cannot pause",
        )
    inst.pause_requested = True
    return {"pausing": inst.id, "name": inst.name, "status": "pause-requested"}


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="pause_run",
        description="Cooperatively pause a running subagent at the next step boundary ('chat' = the chat main instance)",
        cost=1,
    )
    def _pause_run(id_or_name: str) -> dict:
        chat = deps.sessions.instance_for(deps.sessions.active_id())
        return pause_run(deps.spawner, chat, id_or_name)
