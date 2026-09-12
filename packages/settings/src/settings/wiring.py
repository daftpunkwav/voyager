"""Assembly for the settings service: the single wiring source for
standalone (rest.py) and aggregated (packages/host/) runs.

In aggregated mode the assembly root passes in a shared SettingsStore so
that settings of the agent and other services register into one store and
the settings page can render them together. The shared instance is owned by
the caller; wiring does not close it.
"""

from __future__ import annotations

from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .capabilities import DEFS, Deps, init_deps, registry


def wire(
    data_dir: str | Path,
    *,
    bus: EventBus | None = None,
    settings_store: SettingsStore | None = None,
) -> Wiring:
    owns = settings_store is None
    store = settings_store or SettingsStore(Path(data_dir) / "settings.db", bus)
    store.register_fresh(DEFS)  # idempotent: only adds keys not yet registered
    init_deps(Deps(store=store))
    return Wiring(
        registry=registry,
        probe=lambda: {"status": "up"},
        close=store.close if owns else None,
    )
