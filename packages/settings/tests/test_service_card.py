"""Consistency between the service.json capability list and the registry (same
contract as _template; service.json is the single source of truth).
"""

import json
from pathlib import Path

from settings.capabilities import registry

SERVICE_DIR = Path(__file__).parent.parent


def test_service_json_matches_registry() -> None:
    card = json.loads((SERVICE_DIR / "service.json").read_text(encoding="utf-8"))
    assert sorted(card["capabilities"]) == registry.names()
