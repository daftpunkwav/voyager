"""Bind one of the agent's own capabilities as an AgentTool (mechanism).

The agent's governance/observation surface is the same capability registry
the human REST projection mounts (agent.capabilities.registry). A tool built
here runs the capability through the same guard chain the human path uses
(auth -> quota -> validate -> invoke -> audit) with the agent principal as
the actor, so every agent-side change lands in the same audit log with
actor=agent (R6 audit symmetry). Not a bridge: no `agent__` prefix, and each
tool file still declares its own LLM-facing description and permission tier
(write / irreversible) explicitly; only the handler and the input schema are
derived from the capability definition.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from platform_actor import ActorContext
from platform_capability import Registry, capability_input_schema, execute

from agent.runtime.events import AGENT_MAIN
from agent.runtime.trace import current_trace_id
from agent.tools.core.base import AgentTool

#: Audit sinks are wired by the composition root (host); an empty list keeps
#: the guard chain intact without persistence (standalone/test runs).
AuditSinks = list[Any]


def agent_context() -> ActorContext:
    """Agent call context bound to the current trace (or a fresh one)."""
    trace = current_trace_id()
    if trace:
        return ActorContext(actor=AGENT_MAIN, trace_id=trace)
    return ActorContext(actor=AGENT_MAIN)


def capability_tool(
    registry: Registry,
    name: str,
    *,
    description: str,
    audit: AuditSinks | None = None,
    write: bool = False,
    irreversible: bool = False,
    concurrent_safe: bool = False,
    dimension: str = "app",
    guard: Callable[[dict[str, Any]], str | None] | None = None,
) -> AgentTool:
    """AgentTool whose handler executes registry[name] as the agent actor.

    `dimension="app"` routes the call through the in-app policy (allow/deny
    lists, L1 on write, L2 on irreversible). `guard` is an agent-side
    precondition evaluated before execution: it returns a model-facing
    refusal text (the call never reaches the capability) or None to proceed;
    the schema is always derived from the capability definition.
    """
    cap = registry.get(name)

    async def handler(**kw: Any) -> Any:
        if guard is not None:
            refused = guard(kw)
            if refused is not None:
                return refused
        return await execute(registry, name, agent_context(), kw, audit=audit)

    return AgentTool(
        name=name,
        description=description,
        handler=handler,
        schema=capability_input_schema(cap),
        dimension=dimension,
        write=write,
        irreversible=irreversible,
        concurrent_safe=concurrent_safe,
    )


__all__ = ["AuditSinks", "agent_context", "capability_tool"]
