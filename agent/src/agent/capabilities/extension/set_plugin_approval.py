"""set_plugin_approval capability: approve/revoke a plugin (bundle or
per-item).

USER actors only: approval writes the user_only settings
agent.plugins.approved / agent.plugins.approvals, which gate what enters the
agent's own tool surface — a privilege-escalation boundary the settings
layer enforces as well (see the parity exception list).
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps


def _require_user(actor: ActorRef | None) -> None:
    if actor is None or actor.kind is not ActorKind.USER:
        raise ServiceError(
            "agent", ErrorSuffix.FORBIDDEN, "plugin approve/revoke is a user-only operation"
        )


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="set_plugin_approval",
        description="Approve/revoke a plugin. granularity='bundle' approves everything"
        " (all three groups load; MCP only registers as pending);"
        " granularity='item' is per-item: only the checked skills/hooks/mcp"
        " lists load (or '*' for all), an empty selection is rejected, checked"
        " names absent from the manifest are skipped and returned in"
        " skipped. Revoking clears all selections and hot-unloads, and"
        " reclaims the external MCP the plugin registered that has no"
        " approved tools (tools already approved or still used by other"
        " plugins are kept, disclosed in mcp_reclaimed /"
        " mcp_reclaim_skipped). MCP tools still need approval in the"
        " external MCP settings",
        cost=1,
    )
    async def set_plugin_approval(
        name: str,
        approved: bool,
        granularity: str = "bundle",
        skills: object = None,
        hooks: object = None,
        mcp: object = None,
        _actor: ActorRef | None = None,
    ) -> dict:
        _require_user(_actor)
        if granularity not in ("bundle", "item"):
            raise ServiceError(
                "agent",
                ErrorSuffix.INVALID_INPUT,
                f"granularity must be 'bundle' or 'item': {granularity!r}",
            )
        if not approved:
            return await deps.plugins.unapprove(name, _actor)
        if granularity == "bundle":
            return await deps.plugins.approve(name, _actor)
        return await deps.plugins.approve_item(name, _actor, skills=skills, hooks=hooks, mcp=mcp)
