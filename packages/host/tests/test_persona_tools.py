"""Persona capability-surface regression: the allowlist and the tools named in
prompts must both align with the real tool surface.

- Every exact name in tool_allow must really exist in the aggregate Toolbelt (a
  typo or rename turns this red);
- Prefix entries (e.g. notes__*) must match at least one real tool in the roster
  (a dead prefix turns this red);
- Every tool name mentioned in a prompt must be covered by the allowlist (exact
  name or prefix expansion); Lucien is not trimmed, only checked against naming
  real tools.
The aggregate assembly is the source of truth for the tool surface: internal
tools plus {domain}__* injected by the domain bridge (host.bridge).
"""

from pathlib import Path

from agent.personas import PERSONAS
from host.assemble import build


def _allow_covers(allow: tuple[str, ...] | None, tool: str) -> bool:
    """Whether the allowlist covers a tool: exact-name hit or prefix-entry
    expansion hit."""
    if allow is None:
        return True
    return any(
        t == tool or (t.endswith("*") and len(t) > 1 and tool.startswith(t[:-1])) for t in allow
    )


def _persona_tool_audit(agent_app) -> list[str]:
    real = set(agent_app.spawner._toolbelt.names())
    problems: list[str] = []
    for key, persona in PERSONAS.items():
        allow = persona.tool_allow or ()
        problems += [
            f"{key}: dead exact name in allowlist {t}"
            for t in allow
            if not t.endswith("*") and t not in real
        ]
        problems += [
            f"{key}: dead prefix (no roster match) {t}"
            for t in allow
            if t.endswith("*") and len(t) > 1 and not any(n.startswith(t[:-1]) for n in real)
        ]
        mentioned = sorted(t for t in real if t in persona.system_prompt)
        if persona.tool_allow is None:
            problems += [
                f"{key}: prompt names a nonexistent tool {t}" for t in mentioned if t not in real
            ]
            continue
        problems += [
            f"{key}: named in prompt but not covered by the allowlist {t}"
            for t in mentioned
            if not _allow_covers(persona.tool_allow, t)
        ]
        # "Not named in the prompt" is only checked for exact-name entries:
        # prefix expansions are a dynamic roster and are not named individually
        problems += [
            f"{key}: dead allowlist tool (not named in prompt) {t}"
            for t in allow
            if not t.endswith("*") and t not in mentioned
        ]
    return problems


def test_persona_tool_allow_matches_toolbelt(tmp_path: Path) -> None:
    app = build(tmp_path / "data", tmp_path / "ws")
    try:
        problems = _persona_tool_audit(app.state.backend.agent)
    finally:
        app.state.backend.agent.close()
    assert problems == []
