"""uninstall_plugin capability: delete the directory of an unapproved
plugin (approved plugins must be revoked first).

The agent's uninstall_plugin tool binds the same capability under L2
confirmation (directory deletion is irreversible).
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="uninstall_plugin",
        description="Delete the directory of an unapproved plugin; approved plugins"
        " must be revoked first (revocation also reclaims the external MCP"
        " the plugin registered via the safety chain)",
        cost=1,
    )
    async def uninstall_plugin(name: str) -> dict:
        return deps.plugins.uninstall(name)
