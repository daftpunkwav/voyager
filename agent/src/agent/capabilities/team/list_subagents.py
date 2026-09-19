"""list_subagents capability: registered definitions plus alive instances.

`list_subagents()` is the one implementation; the capability and the agent's
list_subagents tool both bind it. Terminal instances are never listed.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.subagent.registry import SubagentRegistry
from agent.subagent.spawn import Spawner


def list_subagents(registry: SubagentRegistry, spawner: Spawner) -> dict:
    return {
        "definitions": [
            {
                "name": d.name,
                "mode": d.mode,
                "description": d.description,
                "persona": d.persona,
                "allowed_tools": list(d.allowed_tools) if d.allowed_tools else None,
                "max_rounds": d.max_rounds,
                "max_tool_calls": d.max_tool_calls,
                "network_mode": d.network_mode,
                "readonly": d.readonly,
                "enabled": d.enabled,
            }
            for d in registry.list()
        ],
        "running": [
            {
                "id": i.id,
                "name": i.name,
                "status": i.status.value,
                "goal": i.task.goal,
                "started_ts": i.state.started_ts,
                "last_step": ((i.state.steps[-1].summary or "")[:120] if i.state.steps else ""),
                "depends_on": list(i.task.depends_on),  # orchestration visibility (T-20.4)
                # Conversational instances are the chat sessions themselves (the
                # user talking to Lucien), not dispatched subagents; consumers
                # use this to keep them out of subagent rosters or label them
                # as the main conversation.
                "conversational": i.task.conversational,
                # Chat session this run belongs to ('' = session-less background
                # work); the frontend filters the panel to the open session.
                "session": i.task.session,
            }
            # Only alive instances are listed: terminal ones (completed/failed/
            # cancelled) stay in spawner.instances for memory introspection but
            # are no longer returned here, so the frontend badge/instance list
            # never shows ghost entries.
            for i in spawner.instances.values()
            if i.status.alive
        ],
    }


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="list_subagents",
        description="Registered subagent definitions + running instances",
    )
    def _list_subagents() -> dict:
        return list_subagents(deps.subagents, deps.spawner)
