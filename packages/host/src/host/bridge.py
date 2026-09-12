"""Bridge from domain capability registries to agent AgentTools.

Tools are named <domain>__<capability>; metadata is passed through (write,
reversible -> irreversible). execute() runs the full capability-framework
guard chain (auth/quota/audit) with the agent principal as the actor. Each
call builds a fresh ActorContext bound to the current trace, so agent
capability calls share a trace with the user.message that triggered them.

This module speaks a structural mount protocol (domain + registry) and does
not import the gateway MountSpec type, so the agent-facing bridge stays
decoupled from the HTTP shell. The returned dict is wrapped by the assembly
root as StaticToolSource("domain", ...) (see agent/contracts.py ToolSource
for the onboarding contract new domains implement).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from agent.runtime.trace import current_trace_id
from agent.tools.core.base import AgentTool
from platform_actor import ActorContext
from platform_capability import capability_input_schema, execute
from platform_contracts import ActorKind, ActorRef

AGENT_ACTOR = ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=("domain:*",))


class MountLike(Protocol):
    """Minimum surface the bridge needs from a mounted domain (read-only, so
    frozen dataclasses such as gateway MountSpec satisfy it)."""

    @property
    def domain(self) -> str: ...

    @property
    def registry(self) -> Any: ...


def agent_context() -> ActorContext:
    """Build the agent call context from the current trace: reuse the active
    trace id, or start a new one."""
    trace = current_trace_id()
    if trace:
        return ActorContext(actor=AGENT_ACTOR, trace_id=trace)
    return ActorContext(actor=AGENT_ACTOR)


def make_domain_tools(
    mounts: Sequence[MountLike],
    *,
    audit: list | None = None,
    quota: list | None = None,
) -> dict[str, AgentTool]:
    """Mount list -> agent tool set. Each handler closure binds the registry and
    capability of its own registration (via default arguments)."""
    tools: dict[str, AgentTool] = {}
    for m in mounts:
        for cap in m.registry.all():

            async def handler(_reg=m.registry, _cap=cap, **kw: Any):
                return await execute(
                    _reg,
                    _cap.name,
                    agent_context(),
                    kw,
                    audit=audit,
                    quota=quota,
                )

            tools[f"{m.domain}__{cap.name}"] = AgentTool(
                name=f"{m.domain}__{cap.name}",
                description=f"[{m.domain}] {cap.description}",
                handler=handler,
                schema=capability_input_schema(cap),
                dimension=cap.dimension,
                write=cap.write,
                irreversible=not cap.reversible,
            )
    return tools
