"""get_settings capability: list the full settings schema (secrets return
has_value only)."""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="get_settings",
        description="List the full settings schema (secrets return has_value only)",
    )
    def get_settings() -> list[dict]:
        return deps.settings.list_schema()
