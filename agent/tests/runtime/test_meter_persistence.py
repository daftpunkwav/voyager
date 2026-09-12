"""Meter persistence: tool rows land as call counts (tokens stay llm-only
for quota), observability split keeps the re-exports stable."""

from __future__ import annotations

from agent.runtime import Meter, MeterRecord
from agent.runtime.meter_store import MeterStore


class TestMeterPersistence:
    def test_tool_rows_persist_counts_but_not_tokens_to_quota(self, tmp_path) -> None:
        store = MeterStore(tmp_path / "meter.db")
        meter = Meter(store=store)
        meter.record(
            MeterRecord(kind="tool", name="read_file", ms=1.0, input_tokens=999, output_tokens=999)
        )
        meter.record(MeterRecord(kind="llm", name="m", ms=1.0, input_tokens=300, output_tokens=70))
        assert meter.tool_calls_today() == 1
        assert meter.tokens_used_today() == 370  # quota reads llm tokens only
        assert store.calls_today(kind="tool") == 1
        meter.close()

    def test_calls_column_migrates_preexisting_db(self, tmp_path) -> None:
        import sqlite3

        db = tmp_path / "old.db"
        legacy = sqlite3.connect(db)
        legacy.execute(
            "CREATE TABLE meter_tokens (day_utc TEXT, kind TEXT, input_tokens INTEGER,"
            " output_tokens INTEGER, PRIMARY KEY (day_utc, kind))"
        )
        legacy.execute("INSERT INTO meter_tokens VALUES ('2026-01-01', 'llm', 5, 5)")
        legacy.commit()
        legacy.close()
        store = MeterStore(db)
        store.add("tool", 0, 0, calls=2)
        assert store.calls_today(kind="tool") == 2
        assert store.tokens_used_today(now=1767225600) == 10  # legacy row intact
        store.close()

    def test_in_memory_meter_counts_today(self) -> None:
        meter = Meter()
        meter.record(MeterRecord(kind="tool", name="grep", ms=1.0))
        meter.record(MeterRecord(kind="tool", name="grep", ms=1.0))
        assert meter.tool_calls_today() == 2

    def test_legacy_reexports_exist(self) -> None:
        from agent.runtime import MeterStore as ReExportedStore
        from agent.runtime import is_quota_exceeded_reply, metered_llm

        assert ReExportedStore is MeterStore
        assert callable(metered_llm) and callable(is_quota_exceeded_reply)
