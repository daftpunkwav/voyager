"""Usage statistics contract: token split, top model, per-day model breakdown,
recent calls, and the in-place migration that adds cached_tokens to older DBs.
"""

import sqlite3

from llm.store import ProviderStore


def _store(tmp_path) -> ProviderStore:
    store = ProviderStore(tmp_path / "llm.db")
    store.upsert(
        {
            "id": "p1",
            "display_name": "Provider One",
            "base_url": "https://example.test/v1",
            "api_format": "chat",
            "models": ["m1", "m2"],
        }
    )
    return store


class TestUsageStatsContract:
    def test_totals_split_cached_from_input(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.record_usage("p1", "m1", 100, 40, cached_tokens=30, caller="agent")
        store.record_usage("p1", "m2", 50, 10, caller="user")
        stats = store.usage_stats(days=1)
        assert stats["totals"] == {
            "input": 150,
            "output": 50,
            "total_tokens": 200,
            "prompt_cached_tokens": 30,
            "prompt_uncached_tokens": 120,
            "completion_tokens": 50,
            "calls": 2,
        }
        # legacy flat fields stay intact for existing consumers
        assert stats["input_tokens"] == 150 and stats["output_tokens"] == 50
        assert stats["calls"] == 2
        assert "cost" not in stats["totals"]

    def test_top_by_model_by_provider_carry_total_tokens(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.record_usage("p1", "m1", 100, 40, cached_tokens=30)
        store.record_usage("p1", "m2", 50, 10)
        store.record_usage("p1", "m2", 5, 1)
        stats = store.usage_stats(days=1)
        assert stats["top"] == {"model": "m1", "total_tokens": 140}
        by_model = {r["model"]: r for r in stats["by_model"]}
        assert by_model["m1"]["total_tokens"] == 140
        assert by_model["m1"]["prompt_cached_tokens"] == 30
        assert by_model["m2"]["total_tokens"] == 66 and by_model["m2"]["calls"] == 2
        (prov,) = stats["by_provider"]
        assert prov["provider"] == "Provider One" and prov["total_tokens"] == 206

    def test_by_day_has_split_and_model_breakdown(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.record_usage("p1", "m1", 100, 40, cached_tokens=30)
        store.record_usage("p1", "m2", 50, 10)
        (day,) = store.usage_stats(days=1)["by_day"]
        assert day["prompt_cached_tokens"] == 30
        assert day["prompt_uncached_tokens"] == 120
        assert day["completion_tokens"] == 50
        assert [m["model"] for m in day["by_model"]] == ["m1", "m2"]  # largest first
        assert day["by_model"][0]["total_tokens"] == 140

    def test_recent_newest_first_with_split(self, tmp_path) -> None:
        store = _store(tmp_path)
        store.record_usage("p1", "m1", 100, 40, cached_tokens=30, caller="agent")
        store.record_usage("p1", "m2", 50, 10, caller="user", ok=False)
        recent = store.usage_stats(days=1)["recent"]
        assert [r["model"] for r in recent] == ["m2", "m1"]
        assert recent[1] == {
            "id": recent[1]["id"],
            "created_at": recent[1]["created_at"],
            "provider": "Provider One",
            "model": "m1",
            "agent_id": "agent",
            "prompt_cached_tokens": 30,
            "prompt_uncached_tokens": 70,
            "completion_tokens": 40,
            "ok": True,
        }
        assert recent[0]["ok"] is False
        assert store.usage_stats(days=1, recent_limit=1)["recent"][0]["model"] == "m2"

    def test_empty_has_no_top(self, tmp_path) -> None:
        stats = _store(tmp_path).usage_stats(days=1)
        assert "top" not in stats and stats["recent"] == [] and stats["by_day"] == []


class TestMigration:
    def test_older_db_gains_cached_tokens_column(self, tmp_path) -> None:
        db = tmp_path / "llm.db"
        conn = sqlite3.connect(db)
        conn.executescript(
            "CREATE TABLE usage (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL,"
            " provider_id TEXT NOT NULL, model TEXT NOT NULL, caller TEXT NOT NULL DEFAULT '',"
            " input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,"
            " ok INTEGER NOT NULL DEFAULT 1);"
            "INSERT INTO usage (ts, provider_id, model, input_tokens, output_tokens)"
            " VALUES (strftime('%s','now'), 'p1', 'm1', 10, 5);"
        )
        conn.commit()
        conn.close()
        store = ProviderStore(db)
        cols = {row[1] for row in store._conn.execute("PRAGMA table_info(usage)")}
        assert "cached_tokens" in cols
        stats = store.usage_stats(days=1)
        assert stats["totals"]["prompt_cached_tokens"] == 0
        assert stats["totals"]["prompt_uncached_tokens"] == 10
