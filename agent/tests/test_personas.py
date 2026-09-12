"""Tests for persona role ids and legacy alias resolution."""

from agent.personas import (
    PERSONAS,
    canonical_persona_key,
    resolve_persona,
)


def test_canonical_five_keys() -> None:
    assert set(PERSONAS) == {
        "orchestrator",
        "recon",
        "explainer",
        "organizer",
        "graph_guide",
    }
    assert PERSONAS["orchestrator"].display_name == "Lucien"
    assert PERSONAS["recon"].display_name == "Iris"


def test_legacy_aliases_resolve() -> None:
    assert canonical_persona_key("lucien") == "orchestrator"
    assert canonical_persona_key("hub") == "orchestrator"
    assert canonical_persona_key("scout") == "recon"
    assert canonical_persona_key("navigator") == "recon"
    assert canonical_persona_key("mentor") == "explainer"
    assert canonical_persona_key("scribe") == "organizer"
    assert canonical_persona_key("atlas") == "graph_guide"
    assert resolve_persona("lucien") is PERSONAS["orchestrator"]
    assert resolve_persona("atlas") is PERSONAS["graph_guide"]
    assert resolve_persona("custom-hunter") is None  # custom names are not in the built-in table
    assert canonical_persona_key("custom-hunter") == "custom-hunter"
