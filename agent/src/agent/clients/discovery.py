"""Read-only module-card discovery for the agent process.

In the monolith, domain tools already go through host.bridge;
this module only reads packages/*/service.json (never connects, never
imports domain code) so the agent can list declared services for external
MCP consumption. Broken or reserved directories are skipped; startup never
breaks.

Skip rules are duplicated here on purpose: agent must not import
host (import-linter agent-no-domain). The reserved-name set mirrors
packages/host/src/host/scan.py plus `gateway` — the gateway card is
assembled by host, so from the agent's read-only viewpoint it is not
an agent-facing service either.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger("agent.clients.discovery")

#: Composition / scaffold dirs that are not agent-facing service cards.
SKIP_DIR_NAMES = frozenset({"platform", "host", "gateway"})


def discover_services(root: str | Path) -> list[dict]:
    """Scan each service directory under root for service.json, returning the
    parsed module cards.

    - Underscore-prefixed directories (e.g. _template) are skipped;
    - reserved names (platform / host / gateway) are skipped;
    - directories without service.json or with a parse failure are skipped
      and logged;
    - results are sorted by directory name for stable, testable output.
    """
    root = Path(root)
    out: list[dict] = []
    if not root.exists():
        return out
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if child.name in SKIP_DIR_NAMES:
            log.debug("skip reserved directory: %s", child.name)
            continue
        card = child / "service.json"
        if not card.is_file():
            log.debug("skip directory without service.json: %s", child.name)
            continue
        try:
            data = json.loads(card.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            log.warning("service.json parse failed, skip: %s", card)
            continue
        if not isinstance(data, dict):
            log.warning("service.json is not an object, skip: %s", card)
            continue
        data.setdefault("name", child.name)
        out.append(data)
    return out
