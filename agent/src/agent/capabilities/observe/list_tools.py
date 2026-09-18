"""list_tools capability: the current tool-surface roster as the model sees
it (candidates for user-built subagent allowlists).

The agent's list_tools tool binds the same capability.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="list_tools",
        description="Current tool-surface roster (candidates for user-built subagent allowlists)",
    )
    def list_tools() -> list[dict]:
        # Roster matches the ToolSpec the LLM sees (built-in tools + domain
        # bridges such as notes__*), plus the dimension/write classification
        # the frontend uses to group and label entries; parameter schemas stay
        # out of the list (token volume) and live behind describe_tool.
        return deps.toolbelt.roster()
