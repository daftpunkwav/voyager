"""LLM wiring: the single wiring source for standalone runs
(rest.py) and aggregate runs (packages/host/).

Aggregate runs may pass in a shared SecretStore (the system-wide encrypted
vault) and a shared SettingsStore (settings registered into the same store);
shared instances are owned by the caller and wiring never closes them.
"""

from __future__ import annotations

from pathlib import Path

from platform_capability import Wiring
from platform_secrets import SecretStore
from platform_settings import SettingsStore

from .capabilities import Deps, init_deps, registry
from .settings import DEFS
from .store import ProviderStore


def wire(
    data_dir: str | Path,
    *,
    secrets: SecretStore | None = None,
    settings_store: SettingsStore | None = None,
) -> Wiring:
    data_dir = Path(data_dir)
    if settings_store is not None:
        settings_store.register_fresh(DEFS)
    store = ProviderStore(data_dir / "llm.db")
    owns_secrets = secrets is None
    secrets = secrets or SecretStore(data_dir / "secrets.db")
    init_deps(Deps(store=store, secrets=secrets, settings=settings_store))

    def close() -> None:
        store.close()
        if owns_secrets:
            secrets.close()

    return Wiring(registry=registry, probe=lambda: {"status": "up"}, close=close)
