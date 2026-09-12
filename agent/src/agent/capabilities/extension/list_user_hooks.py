"""list_user_hooks capability: read-only listing of the hook json files
under workspace/hooks/.

The agent's list_user_hooks tool binds the same capability.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="list_user_hooks",
        description="Read-only listing of the hook json files under workspace/hooks/:"
        " file name / on / enabled / description / whether loaded",
    )
    def list_user_hooks() -> dict:
        return {"items": deps.user_hooks.list()}
