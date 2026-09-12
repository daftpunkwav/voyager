"""Wiring for the office service, shared by standalone and
aggregate deployment.
"""

from __future__ import annotations

from pathlib import Path

from platform_capability import Wiring
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .capabilities import OfficeDeps, init_all, registry
from .settings import DEFS
from .store import DocumentStore


def wire(
    data_dir: str | Path,
    *,
    bus: EventBus | None = None,
    settings_store: SettingsStore | None = None,
) -> Wiring:
    data_dir = Path(data_dir)
    if settings_store is not None:
        settings_store.register_fresh(DEFS)
    store = DocumentStore(data_dir / "office.db")
    init_all(OfficeDeps(store=store, bus=bus))

    return Wiring(registry=registry, probe=lambda: {"status": "up"}, close=store.close)
