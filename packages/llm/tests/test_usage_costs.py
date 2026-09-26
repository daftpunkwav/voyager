"""get_usage_stats capability: read-side (D-06) cost application over the
store's usage statistics — priced models carry cost_usd, unpriced ones carry
no cost field (nothing is invented), and totals are priced only through the
'*' catch-all (totals mix models).

Unit tests: the entry point is the public capability execute(); the store is
real and per-test, the pricing table is injected through the settings
dependency.
"""

from __future__ import annotations

import pytest
from llm.capabilities import Deps, init_deps, registry
from llm.store import ProviderStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER
from platform_secrets import SecretStore

USER = ActorContext(actor=LOCAL_USER)
#: 1M input / 0.1M output tokens: with prices {"input": 2, "output": 10}
#: this is exactly $2 + $1 = $3 (units are USD per 1M tokens).
_BIG_INPUT = 1_000_000
_SMALL_OUTPUT = 100_000


class _Settings:
    def __init__(self, values: dict | None = None) -> None:
        self.values = values or {}

    def get(self, key: str):
        return self.values.get(key)


@pytest.fixture()
def wired(tmp_path):
    store = ProviderStore(tmp_path / "llm.db")
    secrets = SecretStore(tmp_path / "secrets.db", key_material="test-material")
    settings = _Settings()
    init_deps(Deps(store=store, secrets=secrets, settings=settings))
    yield store, settings
    store.close()
    secrets.close()


def _record(store: ProviderStore, pid: str, model: str) -> None:
    """One provider + one usage row with the shared big-token shape."""
    store.upsert(
        {
            "id": pid,
            "display_name": "Provider",
            "base_url": "https://example.test/v1",
            "api_format": "chat",
            "models": [model],
        }
    )
    store.record_usage(pid, model, _BIG_INPUT, _SMALL_OUTPUT)


class TestUsageCosts:
    async def test_priced_models_and_catchall_total(self, wired) -> None:
        store, settings = wired
        settings.values["llm.pricing"] = {
            "m1": {"input": 2, "output": 10},
            "*": {"input": 1, "output": 2},
        }
        _record(store, "p1", "m1")
        stats = await execute(registry, "get_usage_stats", USER, {"days": 1})
        # totals price through the '*' catch-all: $1 + 0.1M * $2/M = $1.2
        assert stats["totals"]["cost_usd"] == pytest.approx(1.2)
        (row,) = stats["by_model"]
        assert row["model"] == "m1" and row["cost_usd"] == pytest.approx(3.0)
        (day,) = stats["by_day"]
        assert day["cost_usd"] == pytest.approx(3.0)

    async def test_totals_uncosted_without_catchall(self, wired) -> None:
        """Totals mix models: without a '*' entry they carry no cost, while
        exactly-priced model rows still do."""
        store, settings = wired
        settings.values["llm.pricing"] = {"m1": {"input": 2, "output": 10}}
        _record(store, "p1", "m1")
        _record(store, "p2", "m2")  # unpriced model
        stats = await execute(registry, "get_usage_stats", USER, {"days": 1})
        assert "cost_usd" not in stats["totals"]
        by_model = {r["model"]: r for r in stats["by_model"]}
        assert by_model["m1"]["cost_usd"] == pytest.approx(3.0)
        assert "cost_usd" not in by_model["m2"]
        # the day aggregates its priced models only
        (day,) = stats["by_day"]
        assert day["cost_usd"] == pytest.approx(3.0)

    async def test_empty_or_missing_table_reports_no_costs(self, wired) -> None:
        store, settings = wired
        _record(store, "p1", "m1")
        stats = await execute(registry, "get_usage_stats", USER, {"days": 1})
        assert "cost_usd" not in stats["totals"]
        assert all("cost_usd" not in r for r in stats["by_model"])

        settings.values["llm.pricing"] = {}  # explicitly empty table: same contract
        stats = await execute(registry, "get_usage_stats", USER, {"days": 1})
        assert all("cost_usd" not in r for r in stats["by_model"])
        assert all("cost_usd" not in d for d in stats["by_day"])

    async def test_recent_limit_clamped_to_at_least_one(self, wired) -> None:
        store, settings = wired
        settings.values["llm.pricing"] = {"m1": {"input": 2, "output": 10}}
        _record(store, "p1", "m1")
        _record(store, "p1", "m1")
        stats = await execute(registry, "get_usage_stats", USER, {"days": 1, "recent_limit": 0})
        assert len(stats["recent"]) == 1

    async def test_malformed_rows_are_skipped_not_fatal(self, tmp_path) -> None:
        """Corrupt aggregate rows (a non-dict day, model rows without a model
        id) degrade to partial costs instead of killing the whole read."""

        class _FakeStore:
            def usage_stats(self, days: int, recent_limit: int = 20) -> dict:
                return {
                    "totals": {"input": 10, "output": 5},
                    "by_model": ["garbage", {"input": 10, "output": 5}],
                    "by_day": [
                        "garbage",
                        {
                            "input": 10,
                            "output": 5,
                            "by_model": [
                                "garbage",
                                {"model": "m1", "input": 10, "output": 5},
                            ],
                        },
                    ],
                    "recent": [],
                }

        secrets = SecretStore(tmp_path / "secrets.db", key_material="test-material")
        settings = _Settings({"llm.pricing": {"m1": {"input": 2, "output": 10}}})
        init_deps(Deps(store=_FakeStore(), secrets=secrets, settings=settings))  # type: ignore[arg-type]
        stats = await execute(registry, "get_usage_stats", USER, {"days": 1})
        assert "cost_usd" not in stats["totals"]  # no '*' entry: totals uncosted
        assert all("cost_usd" not in r for r in stats["by_model"] if isinstance(r, dict))
        (day,) = [d for d in stats["by_day"] if isinstance(d, dict)]
        assert day["cost_usd"] == pytest.approx(0.00007)  # 10*$2/M + 5*$10/M
        secrets.close()

    async def test_no_pricing_without_settings_dependency(self, tmp_path) -> None:
        """A settings-less wiring (None) must not invent costs: the read side
        needs the price table, and its absence degrades to token-only stats."""
        store = ProviderStore(tmp_path / "llm.db")
        secrets = SecretStore(tmp_path / "secrets.db", key_material="test-material")
        init_deps(Deps(store=store, secrets=secrets, settings=None))
        try:
            _record(store, "p1", "m1")
            stats = await execute(registry, "get_usage_stats", USER, {"days": 1})
            assert "cost_usd" not in stats["totals"]
            assert stats["totals"]["input"] == _BIG_INPUT
        finally:
            store.close()
            secrets.close()
