"""Assembly planning for the composition root: decide which scanned
domains get wired, in what order, and register card-declared settings.

Responsibilities:
- Select the enabled domain subset (card flag, host.domains.enabled, or
  ENABLE_DOMAINS whitelist)
- Topologically order cards by depends_on (Kahn's algorithm, cycle = refuse)
- Discover gateway-role settings modules and register their SettingDefs

Pure planning over module cards: no wiring, no shared facilities, no gateway
import. The wiring loop lives in assemble.py.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import os
from collections.abc import Sequence

from platform_contracts import ServiceError
from platform_settings import SettingsStore

from .scan import ServiceCard

log = logging.getLogger("host.plan")


def enabled_from_settings(store: SettingsStore) -> tuple[str, ...] | None:
    """Read host.domains.enabled. None means "use card defaults".

    A missing key, a non-list value, or an empty list all mean defaults so a
    broken setting cannot silently unmount the whole workbench.
    """
    try:
        raw = store.get("host.domains.enabled")
    except ServiceError:
        log.warning("host.domains.enabled unreadable, using card defaults")
        return None
    if not raw:
        return None
    if not isinstance(raw, list) or any(not isinstance(v, str) for v in raw):
        log.warning("host.domains.enabled is not a string list, ignored: %r", raw)
        return None
    names = tuple(v.strip() for v in raw if v.strip())
    return names or None


def select_enabled(
    cards: list[ServiceCard],
    *,
    env_raw: str | None = None,
    enabled_names: Sequence[str] | None = None,
) -> list[ServiceCard]:
    """Pick the domains to wire.

    Precedence: ENABLE_DOMAINS (process env, or ``env_raw`` in tests) wins;
    else ``enabled_names`` (settings whitelist); else each card's
    ``enabled_by_default``. Gateway-role cards are never wired: the gateway is
    the mount shell the composition root imports directly, not an agent-facing
    domain. Unknown whitelist names are logged and ignored.
    """
    raw = (os.environ.get("ENABLE_DOMAINS", "") if env_raw is None else env_raw).strip()
    if raw:
        wanted = {s.strip() for s in raw.split(",") if s.strip()}
        return _whitelist(cards, wanted, source="ENABLE_DOMAINS")
    if enabled_names:
        wanted = {s.strip() for s in enabled_names if s.strip()}
        if wanted:
            return _whitelist(cards, wanted, source="host.domains.enabled")
    return [c for c in cards if c.enabled_by_default and c.role == "domain"]


def _whitelist(
    cards: list[ServiceCard],
    wanted: set[str],
    *,
    source: str,
) -> list[ServiceCard]:
    known = {c.domain for c in cards if c.role == "domain"}
    unknown = wanted - known
    if unknown:
        log.warning("%s names not scanned as domains, ignored: %s", source, sorted(unknown))
    return [c for c in cards if c.domain in wanted and c.role == "domain"]


def topo_order(cards: list[ServiceCard]) -> list[ServiceCard]:
    """Order enabled cards so dependencies start first (Kahn's algorithm; output
    stays alphabetically stable among ready nodes). depends_on only influences
    start order — it never licenses implementation imports between domains.
    Dependencies that are missing or disabled are ignored with a warning; a
    cycle fails startup (assembly cannot proceed unambiguously).
    """
    by_name = {c.domain: c for c in cards}
    deps = {c.domain: [d for d in c.depends_on if d in by_name] for c in cards}
    for c in cards:
        missing = set(c.depends_on) - set(deps[c.domain])
        if missing:
            log.warning(
                "domain %s depends_on names not enabled, ignored: %s",
                c.domain,
                sorted(missing),
            )
    ordered: list[ServiceCard] = []
    remaining = dict(deps)
    while remaining:
        ready = sorted(n for n, ds in remaining.items() if not ds)
        if not ready:
            raise RuntimeError(
                f"service card depends_on contains a cycle, "
                f"refusing to assemble: {sorted(remaining)}"
            )
        for name in ready:
            ordered.append(by_name[name])
            remaining.pop(name)
        for ds in remaining.values():
            ds[:] = [d for d in ds if d not in ready]
    return ordered


def register_gateway_settings(cards: list[ServiceCard], store: SettingsStore) -> None:
    """Register settings of gateway-role domains. The gateway has no wiring of
    its own (it is the mount shell, imported by the composition root), so its
    SettingDefs are discovered from <module>.settings when present.
    """
    for card in cards:
        if card.role != "gateway":
            continue
        settings_mod = f"{card.module}.settings"
        if importlib.util.find_spec(settings_mod) is None:
            log.debug("gateway %s has no settings module, skip", card.domain)
            continue
        try:
            module = importlib.import_module(settings_mod)
        except Exception:
            log.exception("failed to import %s, skip settings", settings_mod)
            continue
        defs = getattr(module, "DEFS", None)
        if defs is None:
            log.warning("%s has no DEFS, skip", settings_mod)
            continue
        store.register_fresh(defs)
