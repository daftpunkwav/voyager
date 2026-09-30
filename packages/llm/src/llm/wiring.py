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
from .store import USAGE_RETENTION_DAYS, ProviderStore


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
    # Startup purge of usage rows past the retention window (90d, mirrors
    # meter.db): one row is written per LLM call, so the table would grow
    # forever without it.
    store.purge_usage_older_than_days(USAGE_RETENTION_DAYS)
    owns_secrets = secrets is None
    secrets = secrets or SecretStore(data_dir / "secrets.db")
    init_deps(Deps(store=store, secrets=secrets, settings=settings_store))

    def close() -> None:
        store.close()
        if owns_secrets:
            secrets.close()

    return Wiring(registry=registry, probe=lambda: {"status": "up"}, close=close)
