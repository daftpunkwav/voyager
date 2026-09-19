"""register_subagent capability: persist a user-built subagent definition
(mode / tool surface / tier overrides).

`register_subagent()` is the one implementation; the capability and the
agent's register_subagent tool both bind it.
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.runtime.current import current_instance
from agent.subagent.registry import SubagentDef, SubagentRegistry
from agent.subagent.surface import surface_misses


def register_subagent(
    registry: SubagentRegistry,
    *,
    name: str,
    description: str,
    mode: str = "react",
    allowed_tools: list[str] | None = None,
    persona: str = "",
    max_rounds: int | None = None,
    max_tool_calls: int | None = None,
    network_mode: str = "",
    readonly: bool = False,
    enabled: bool = True,
) -> dict:
    """Save a SubagentDef; mode must be one of the seven mode enums
    (invalid values raise AGENT.INVALID_INPUT).

    allowed_tools is a capability-surface whitelist trim (Toolbelt.trimmed):
    without write_file the instance genuinely cannot write — this is not a
    prompt-level constraint; None = no trimming. readonly additionally
    drops every write/irreversible tool at spawn (default-deny review
    bots), narrowing whatever allowed_tools yields.
    max_rounds / max_tool_calls / network_mode are permission-tier overrides:
    omitted round limits follow the global setting, an empty network tier
    inherits the global one; on spawn, only stricter values are allowed.
    enabled=False keeps the definition registered and listed but dispatch
    refuses it until re-enabled (settings toggle).
    """
    d = SubagentDef(
        name=name,
        description=description,
        mode=mode,
        persona=persona,
        allowed_tools=tuple(allowed_tools) if allowed_tools else None,
        max_rounds=max_rounds,
        max_tool_calls=max_tool_calls,
        network_mode=network_mode or "",
        readonly=readonly,
        enabled=enabled,
    )
    registry.save(d)
    return {
        "name": d.name,
        "mode": d.mode,
        "allowed_tools": allowed_tools,
        "max_rounds": d.max_rounds,
        "max_tool_calls": d.max_tool_calls,
        "network_mode": d.network_mode,
        "readonly": d.readonly,
        "enabled": d.enabled,
    }


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="register_subagent",
        description="Register a user-built subagent definition",
        cost=2,
    )
    def _register_subagent(
        name: str,
        description: str,
        mode: str = "react",
        allowed_tools: list[str] | None = None,
        persona: str = "",
        max_rounds: int | None = None,
        max_tool_calls: int | None = None,
        network_mode: str = "",
        readonly: bool = False,
        enabled: bool = True,
        _actor: ActorRef | None = None,
    ) -> dict:
        # Assignment-surface validation (agent calls only): a definition
        # registered by a narrowed instance may not promise tools that
        # instance does not have — the human path (full surface) skips this.
        # Dispatch re-checks against the dispatching surface anyway, so this
        # is early, readable feedback, not the enforcement boundary.
        if (
            allowed_tools
            and _actor is not None
            and _actor.kind is ActorKind.AGENT
            and (inst := current_instance.get()) is not None
        ):
            missing = surface_misses(allowed_tools, inst.toolbelt.names())
            if missing:
                raise ServiceError(
                    "agent",
                    ErrorSuffix.FORBIDDEN,
                    f"tools not available on this instance's surface: {', '.join(missing)}",
                    hint="register an allowlist within this instance's own tools",
                )
        return register_subagent(
            deps.subagents,
            name=name,
            description=description,
            mode=mode,
            allowed_tools=allowed_tools,
            persona=persona,
            max_rounds=max_rounds,
            max_tool_calls=max_tool_calls,
            network_mode=network_mode,
            readonly=readonly,
            enabled=enabled,
        )
