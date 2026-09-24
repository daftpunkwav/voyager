"""Persona presets (pure data, loaded from definitions/*.toml): structural
IDs named by responsibility; display names stay in Persona.display_name.

The built-in roles are data files (one TOML per role, codex builtins shape)
rather than code: adding or tuning a role never touches the loader. Legacy
keys (lucien/iris/hub/scout/...) resolve to responsibility IDs via ALIASES
so persisted sessions can migrate.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from agent.personas.base import Persona

_DEFINITIONS_DIR = Path(__file__).parent / "definitions"

#: Public alias: where the built-in role files live (data, not code)
DEFINITIONS_DIR = _DEFINITIONS_DIR


def _load_persona(path: Path) -> Persona:
    """One definition file -> one Persona; a missing key field fails loudly
    (a broken role file is an assembly error, not a silent skip)."""
    with open(path, "rb") as f:
        data = tomllib.load(f)
    tool_allow = data.get("tool_allow")
    return Persona(
        key=str(data["key"]),
        display_name=str(data["display_name"]),
        style=str(data["style"]),
        system_prompt=str(data["system_prompt"]),
        default_mode=str(data.get("default_mode", "react")),
        tool_allow=tuple(str(t) for t in tool_allow) if tool_allow is not None else None,
    )


def _load_all(directory: Path) -> dict[str, Persona]:
    out: dict[str, Persona] = {}
    for path in sorted(directory.glob("*.toml")):
        persona = _load_persona(path)
        if persona.key in out:
            # Two files claiming one structural ID is an authoring error, not
            # a last-wins merge - fail at import while the mistake is fresh
            raise ValueError(f"duplicate persona key {persona.key!r}: {path.name}")
        out[persona.key] = persona
    return out


_PERSONAS = _load_all(_DEFINITIONS_DIR)

# Display-name constant aliases (tests and old imports); .key is the structural ID
ORCHESTRATOR = _PERSONAS["orchestrator"]
RECON = _PERSONAS["recon"]
EXPLAINER = _PERSONAS["explainer"]
ORGANIZER = _PERSONAS["organizer"]
GRAPH_GUIDE = _PERSONAS["graph_guide"]

# Legacy python-module names kept importable (removed data modules)
LUCIEN = ORCHESTRATOR
IRIS = RECON
ELIO = EXPLAINER
MIYAI = ORGANIZER
ATLAS = GRAPH_GUIDE

PERSONAS: dict[str, Persona] = dict(_PERSONAS)

#: Resident team: personas that share every chat session as group-chat members.
#: The orchestrator is the designated speaker (default addressee of user
#: messages); the others answer @-mentions and handoffs and speak under their
#: own name in the shared transcript.
TEAM_KEYS: tuple[str, ...] = (
    "orchestrator",
    "recon",
    "explainer",
    "organizer",
    "graph_guide",
)

#: Legacy structural IDs / frontend seven-role names -> responsibility IDs
ALIASES: dict[str, str] = {
    "lucien": "orchestrator",
    "hub": "orchestrator",
    "iris": "recon",
    "scout": "recon",
    "navigator": "recon",
    "elio": "explainer",
    "mentor": "explainer",
    "miyai": "organizer",
    "curator": "organizer",
    "scribe": "organizer",
    "atlas": "graph_guide",
}


def canonical_persona_key(key: str) -> str:
    """Fold an alias into its responsibility ID; unknown keys pass through
    unchanged (user-defined subagent names)."""
    return ALIASES.get(key, key)


def resolve_persona(key: str) -> Persona | None:
    """Look up a built-in persona by responsibility ID or legacy alias; None
    when not found."""
    if not key:
        return None
    return PERSONAS.get(canonical_persona_key(key))


__all__ = [
    "ALIASES",
    "ATLAS",
    "ELIO",
    "EXPLAINER",
    "GRAPH_GUIDE",
    "IRIS",
    "LUCIEN",
    "MIYAI",
    "ORCHESTRATOR",
    "ORGANIZER",
    "PERSONAS",
    "RECON",
    "TEAM_KEYS",
    "Persona",
    "canonical_persona_key",
    "resolve_persona",
]
