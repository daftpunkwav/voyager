"""list_personas capability: the persona preset catalog (team page data
source).

Deliberately has no agent tool: the persona roster is already resident in
the system prompt (see the parity exception list).
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps
from agent.personas import PERSONAS


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="list_personas",
        description="Persona preset catalog (data source for the team page)",
    )
    def list_personas() -> list[dict]:
        return [
            {
                "key": p.key,
                "id": p.key,
                "display_name": p.display_name,
                "style": p.style,
                "default_mode": p.default_mode,
                "tool_allow": list(p.tool_allow) if p.tool_allow else None,
                "system_prompt": p.system_prompt,
            }
            for p in PERSONAS.values()
        ]
