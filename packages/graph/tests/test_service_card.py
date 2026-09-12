"""service.json capability list matches the registry (single source of truth)."""

import json
from pathlib import Path

from graph.capabilities import registry

SERVICE_DIR = Path(__file__).parent.parent


def test_service_json_matches_registry() -> None:
    card = json.loads((SERVICE_DIR / "service.json").read_text(encoding="utf-8"))
    assert sorted(card["capabilities"]) == registry.names()
