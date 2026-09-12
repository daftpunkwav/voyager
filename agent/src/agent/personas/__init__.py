"""Persona presets (pure data): structural IDs named by responsibility;
display names stay in Persona.display_name.

Legacy keys (lucien/iris/hub/scout/...) resolve to responsibility IDs via
ALIASES so persisted sessions can migrate.
"""

from agent.personas.base import Persona
from agent.personas.explainer import EXPLAINER
from agent.personas.graph_guide import GRAPH_GUIDE
from agent.personas.orchestrator import ORCHESTRATOR
from agent.personas.organizer import ORGANIZER
from agent.personas.recon import RECON

# Display-name constant aliases (tests and old imports); .key is the structural ID
LUCIEN = ORCHESTRATOR
IRIS = RECON
ELIO = EXPLAINER
MIYAI = ORGANIZER
ATLAS = GRAPH_GUIDE

PERSONAS: dict[str, Persona] = {
    p.key: p for p in (ORCHESTRATOR, RECON, EXPLAINER, ORGANIZER, GRAPH_GUIDE)
}

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
    "Persona",
    "canonical_persona_key",
    "resolve_persona",
]
