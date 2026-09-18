"""describe_tool capability: full metadata for one tool roster entry.

Parameter schemas stay out of list_tools (schema volume is exactly what
graded activation guards), so the frontend tool catalog fetches them
per expanded row here instead.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="describe_tool",
        description="Full metadata for one tool roster entry (description, classification, parameter schema)",
    )
    def describe_tool(name: str) -> dict:
        return deps.toolbelt.describe(name)
