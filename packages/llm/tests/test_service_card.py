"""service.json capability card <-> registry consistency (single source of
truth for the exposed surface).
"""

import json
from pathlib import Path

from llm.capabilities import registry

SERVICE_DIR = Path(__file__).parent.parent


def test_service_json_matches_registry() -> None:
    card = json.loads((SERVICE_DIR / "service.json").read_text(encoding="utf-8"))
    assert sorted(card["capabilities"]) == registry.names()
