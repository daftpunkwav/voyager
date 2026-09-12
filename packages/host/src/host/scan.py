"""Domain discovery for the composition root: read one service.json
module card per directory under the domain root and normalize it into a
ServiceCard value.

Responsibilities:
- Read and validate module cards (sorted, stable output)
- Normalize declared fields: needs / depends_on / enabled_by_default / role
- Skip scaffolding (_-prefixed), reserved composition dirs (platform / host),
  and broken cards without failing startup

This module must not import any domain implementation: discovery reads
cards, never code. Whether a card gets wired, and in which order, is an
assembly decision (host.plan / assemble), not a discovery one.

Gateway-role cards are returned as-is so the composition root can register
their settings; filtering them out of the agent tool surface is plan's job.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("host.scan")

#: Directory names that must never become domains even if they carry a card.
#: ``gateway`` is intentionally not listed: its card is scanned so host can
#: register gateway settings, then excluded from wiring by role.
SKIP_DIR_NAMES = frozenset({"platform", "host"})


@dataclass(frozen=True)
class ServiceCard:
    """Normalized module card: one domain's declaration of what it is and what
    it needs from the composition root.

    ``domain`` is the directory name and doubles as the assembly identity:
    mount prefix (/api/<domain>), agent tool prefix (<domain>__*), wiring key
    and depends_on reference all use it. The card's ``name`` is display-only.
    """

    domain: str
    module: str  # importable module path, e.g. "notes"
    name: str
    version: str
    protocol: str
    port: int | None
    capabilities: tuple[str, ...] = ()
    subscribes: tuple[str, ...] = ()
    publishes: tuple[str, ...] = ()
    status: str | None = None
    enabled_by_default: bool = True
    needs: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    role: str = "domain"  # "domain" | "gateway"; gateways are never wired


def _str_list(raw: object) -> tuple[str, ...] | None:
    if not isinstance(raw, list) or any(not isinstance(v, str) for v in raw):
        return None
    return tuple(raw)


def _parse_card(child: Path, module_prefix: str) -> ServiceCard | None:
    """Parse one service.json; return None (with a warning) for any structurally
    invalid card. A half-parsed card must not be trusted for assembly.

    A missing card is a debug skip (normal for platform/host/scaffold leftovers),
    not a warning: warnings are reserved for a card that exists but is broken.
    """
    card_path = child / "service.json"
    if not card_path.is_file():
        log.debug("skip directory without service.json: %s", child.name)
        return None
    try:
        raw = json.loads(card_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("service.json unreadable, skip: %s (%s)", card_path, exc)
        return None
    if not isinstance(raw, dict):
        log.warning("service.json is not an object, skip: %s", card_path)
        return None
    for key in ("version", "protocol"):
        if not isinstance(raw.get(key), str):
            log.warning("service.json field %s missing or not a string, skip: %s", key, card_path)
            return None
    port = raw.get("port")
    if port is not None and not isinstance(port, int):
        log.warning("service.json field port is not an integer, skip: %s", card_path)
        return None
    name_raw = raw.get("name", child.name)
    if not isinstance(name_raw, str) or not name_raw.strip():
        log.warning("service.json field name is not a non-empty string, skip: %s", card_path)
        return None
    status = raw.get("status")
    if status is not None and not isinstance(status, str):
        log.warning("service.json field status is not a string, skip: %s", card_path)
        return None
    capabilities = _str_list(raw.get("capabilities", []))
    subscribes = _str_list(raw.get("subscribes", []))
    publishes = _str_list(raw.get("publishes", []))
    needs = _str_list(raw.get("needs", []))
    depends_on = _str_list(raw.get("depends_on", []))
    if (
        capabilities is None
        or subscribes is None
        or publishes is None
        or needs is None
        or depends_on is None
    ):
        log.warning("service.json list field invalid, skip: %s", card_path)
        return None
    enabled = raw.get("enabled_by_default", True)
    if not isinstance(enabled, bool):
        log.warning("service.json field enabled_by_default is not bool, skip: %s", card_path)
        return None
    role = raw.get("role", "domain")
    if role not in ("domain", "gateway"):
        log.warning("service.json field role invalid (%s), skip: %s", role, card_path)
        return None
    return ServiceCard(
        domain=child.name,
        module=f"{module_prefix}.{child.name}" if module_prefix else child.name,
        name=name_raw.strip(),
        version=raw["version"],
        protocol=raw["protocol"],
        port=port,
        capabilities=capabilities,
        subscribes=subscribes,
        publishes=publishes,
        status=status,
        enabled_by_default=enabled,
        needs=needs,
        depends_on=depends_on,
        role=role,
    )


def scan(root: str | Path, module_prefix: str) -> list[ServiceCard]:
    """Scan each directory under root for service.json, returning normalized
    cards sorted by directory name (stable, testable output).

    ``module_prefix`` is the importable parent package of the domains. The
    production layout installs each domain as a top-level package, so the
    composition root passes an empty prefix and the module is the directory
    name; a non-empty prefix serves test namespace roots.

    - Underscore-prefixed directories (scaffolding, e.g. _template) are skipped;
    - reserved names in SKIP_DIR_NAMES are skipped even if they have a card;
    - directories without a card, or with a broken one, are skipped and logged;
    - a missing root yields an empty list;
    - gateway-role cards are returned as-is; filtering by role is the
      assembly's decision.
    """
    root = Path(root)
    if not root.exists():
        return []
    out: list[ServiceCard] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        if child.name in SKIP_DIR_NAMES:
            log.debug("skip reserved composition directory: %s", child.name)
            continue
        card = _parse_card(child, module_prefix)
        if card is not None:
            out.append(card)
    return out
