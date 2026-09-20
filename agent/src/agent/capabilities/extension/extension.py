"""extension capability: plugins / external MCP / user hooks in one surface.

kind×action grid:
    plugin: list / install / uninstall
    mcp:    list / preview
    hook:   list / reload

Installing does not auto-approve — an installed plugin stays unloaded until
approved through set_plugin_approval (user-only, privileged boundary along
with add_mcp_server / approve_mcp_tools / remove_mcp_server, which stay
separate capabilities). Reload reinstalls whatever the agent may have
written into the hooks directory. The agent's extension tool binds this same
capability.
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps

_KINDS = ("plugin", "mcp", "hook")
_ACTIONS = {
    "plugin": ("list", "install", "uninstall"),
    "mcp": ("list", "preview"),
    "hook": ("list", "reload"),
}


async def extension_action(
    deps: CapabilityDeps,
    *,
    kind: str,
    action: str,
    id: str = "",
    name: str = "",
    zip_path: str = "",
    source_dir: str = "",
    overwrite: bool = False,
) -> dict | list:
    """Dispatch one extension action against plugins/MCP/user-hooks managers."""
    if kind not in _KINDS:
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"unknown kind: {kind!r}",
            hint=f"valid kinds: {', '.join(_KINDS)}",
        )
    if action not in _ACTIONS[kind]:
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"unknown action: {action!r} for kind {kind!r}",
            hint=f"valid actions for {kind}: {', '.join(_ACTIONS[kind])}",
        )
    key = f"{kind}.{action}"
    if key == "plugin.list":
        return {"items": deps.plugins.list()}
    if key == "plugin.install":
        return deps.plugins.install(zip_path=zip_path, source_dir=source_dir, overwrite=overwrite)
    if key == "plugin.uninstall":
        return deps.plugins.uninstall(name)
    if key == "mcp.list":
        return deps.mcp.list_state()
    if key == "mcp.preview":
        preview = await deps.mcp.preview(id)  # raises AGENT.UNAVAILABLE with a readable message
        return {"id": id, "preview": preview}
    if key == "hook.list":
        return {"items": deps.user_hooks.list()}
    return deps.user_hooks.reload()  # hook.reload (sync manager call)


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="extension",
        description=(
            "Plugins / external MCP / user hooks: kind=plugin action list|install"
            "(zip_path|source_dir,overwrite)|uninstall(name); kind=mcp action"
            " list|preview(id); kind=hook action list|reload. Install does not"
            " approve; approval stays user-only"
        ),
    )
    async def extension(
        kind: str,
        action: str,
        id: str = "",
        name: str = "",
        zip_path: str = "",
        source_dir: str = "",
        overwrite: bool = False,
    ) -> dict | list:
        return await extension_action(
            deps,
            kind=kind,
            action=action,
            id=id,
            name=name,
            zip_path=zip_path,
            source_dir=source_dir,
            overwrite=overwrite,
        )
