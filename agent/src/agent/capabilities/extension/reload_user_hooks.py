"""reload_user_hooks capability: reload the declarative user hooks under
workspace/hooks/ without a restart.

The directory is pinned to workspace/hooks as wired at build_agent time and
the capability takes no path parameter (prevents loading arbitrary json
files as hooks). The agent's reload_user_hooks tool binds the same
capability under L2 confirmation (a reload activates whatever the agent may
have written into the hooks directory).
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="reload_user_hooks",
        description="Reload the declarative user hooks under workspace/hooks/: no restart"
        " needed — unloads by the user: prefix and reinstalls, and domain event"
        " subscriptions converge via the existing sync (subscriptions of"
        " approved plugins are unaffected). Returns loaded (count loaded),"
        " event_patterns (current full subscription list), and skipped"
        " (unparseable files)",
        cost=1,
    )
    async def reload_user_hooks() -> dict:
        return deps.user_hooks.reload()
