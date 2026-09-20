"""skill capability: the human REST surface for the skill domain — one
action parameter covers load/propose.

Same name and same operations as the agent's skill tool — both bind
skill_ops (one implementation, two drivers). list_skills stays a separate
resident-prompt capability (no tool, frozen parity exception).
"""

from __future__ import annotations

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from agent.capabilities.deps import CapabilityDeps
from agent.tools.skill.skill_ops import load_skill_text, propose_skill


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="skill",
        description=(
            "Skill domain: action load (name — full text on demand) or propose"
            " (name lowercase kebab-case, description, content Markdown —"
            " persists into the skill library, indexed immediately)"
        ),
    )
    def skill(action: str, name: str = "", description: str = "", content: str = "") -> dict:
        if action == "load":
            return load_skill_text(deps.skills, name)
        if action == "propose":
            return propose_skill(deps.skills_dir, name, description, content)
        raise ServiceError(
            "agent",
            ErrorSuffix.INVALID_INPUT,
            f"unknown action: {action!r}",
            hint="valid actions: load/propose",
        )
