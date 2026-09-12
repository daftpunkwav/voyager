"""install_plugin capability: copy a plugin (zip or local directory) into
plugins/ without approving it.

Installing does not auto-approve — an installed plugin shows up in
list_plugins but stays unloaded until approved through set_plugin_approval
(which remains user-only). The agent's install_plugin tool binds the same
capability under L2 confirmation.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="install_plugin",
        description="Install a plugin (zip_path=server-side absolute path, usually"
        " uploaded via /api/uploads; or source_dir=absolute path of a local"
        " directory, either one). The source must be inside the working"
        " directory or an additional read-only/read-write root. Validates"
        " manifest and path safety (rejects zip slip, contains escapes,"
        " symlinks, size/count limits); same-name conflicts are rejected by"
        " default and only overwritten with explicit overwrite=true;"
        " approved plugins must be revoked first. After copying into"
        " plugins/ it is immediately visible to list_plugins but stays"
        " unloaded until approved — approval still goes through"
        " set_plugin_approval",
        cost=1,
    )
    async def install_plugin(
        zip_path: str = "",
        source_dir: str = "",
        overwrite: bool = False,
    ) -> dict:
        return deps.plugins.install(zip_path=zip_path, source_dir=source_dir, overwrite=overwrite)
