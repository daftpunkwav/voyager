"""Tests for Meter token-usage persistence (resource dimension): daily quotas
survive restarts.

- MeterStore: accumulates per (UTC day, kind) into meter.db; UTC day boundaries are not
  summed together.
- Meter + store: record writes through synchronously; tokens_used_today reads only the
  store when one exists (no double counting).
- build_agent restart: rebuilding with the same data_dir keeps usage intact and quota
  blocking still applies.
"""

import time
from datetime import UTC, datetime

from agent.llm import FakeLLM, LLMReply, Usage
from agent.main import build_agent
from agent.runtime import Meter, MeterRecord, MeterStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER

USER_CTX = ActorContext(actor=LOCAL_USER)


def _ts(*args: int) -> float:
    """UTC (year, month, day, hour, minute) -> epoch seconds, for pinning moments in tests."""
    y, mo, d, h, mi = args
    return datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp()


def _llm_rec(inp: int = 0, out: int = 0, ts: float | None = None) -> MeterRecord:
    return MeterRecord(
        kind="llm",
        name="default",
        ms=1.0,
        input_tokens=inp,
        output_tokens=out,
        ts=ts if ts is not None else _ts(2026, 1, 15, 12, 0),
    )


class TestMeterStore:
    def test_add_and_read_today(self, tmp_path) -> None:
        store = MeterStore(tmp_path / "meter.db")
        try:
            store.add("llm", 100, 20, ts=_ts(2026, 1, 15, 8, 0))
            store.add("llm", 50, 0, ts=_ts(2026, 1, 15, 23, 0))
            assert store.tokens_used_today(now=_ts(2026, 1, 15, 12, 0)) == 170
        finally:
            store.close()

    def test_crosses_utc_midnight(self, tmp_path) -> None:
        store = MeterStore(tmp_path / "meter.db")
        try:
            store.add("llm", 100, 0, ts=_ts(2026, 1, 15, 23, 59))
            store.add("llm", 40, 10, ts=_ts(2026, 1, 16, 0, 1))
            assert store.tokens_used_today(now=_ts(2026, 1, 16, 8, 0)) == 50
            assert store.tokens_used_today(now=_ts(2026, 1, 15, 23, 59)) == 100
        finally:
            store.close()

    def test_reopen_keeps_totals(self, tmp_path) -> None:
        """Close and reopen the same database: totals persist (the essence of persistence)."""
        store = MeterStore(tmp_path / "meter.db")
        store.add("llm", 30, 12, ts=_ts(2026, 1, 15, 8, 0))
        store.close()
        store2 = MeterStore(tmp_path / "meter.db")
        try:
            assert store2.tokens_used_today(now=_ts(2026, 1, 15, 20, 0)) == 42
        finally:
            store2.close()

    def test_only_llm_kind_counted(self, tmp_path) -> None:
        """The daily total counts only llm rows (tool rows are not persisted)."""
        store = MeterStore(tmp_path / "meter.db")
        try:
            store.add("llm", 10, 0, ts=_ts(2026, 1, 15, 8, 0))
            store.add("tool", 999, 999, ts=_ts(2026, 1, 15, 8, 0))
            assert store.tokens_used_today(now=_ts(2026, 1, 15, 9, 0)) == 10
        finally:
            store.close()

    def test_purge_older_than_days(self, tmp_path) -> None:
        """purge(90): deletes rows older than today-90; the day exactly 90 days ago and today are kept."""
        store = MeterStore(tmp_path / "meter.db")
        try:
            now = _ts(2026, 1, 15, 12, 0)
            store.add("llm", 100, 0, ts=_ts(2025, 10, 6, 8, 0))  # 101 days ago -> deleted
            store.add("llm", 40, 0, ts=_ts(2025, 10, 16, 8, 0))  # 91 days ago -> deleted
            store.add("llm", 7, 0, ts=_ts(2025, 10, 17, 8, 0))  # exactly 90 days ago -> kept
            store.add("llm", 5, 3, ts=now)  # today -> kept
            assert store.purge_older_than_days(90, now=now) == 2
            assert store.tokens_used_today(now=now) == 8  # today total unchanged
            assert store.tokens_used_today(now=_ts(2025, 10, 17, 9, 0)) == 7
            assert store.tokens_used_today(now=_ts(2025, 10, 6, 9, 0)) == 0
        finally:
            store.close()


class TestMeterWithStore:
    def test_record_writes_through(self, tmp_path) -> None:
        """After record, the store and tokens_used_today agree; in-memory totals keep working as before."""
        store = MeterStore(tmp_path / "meter.db")
        meter = Meter(store=store)
        try:
            meter.record(_llm_rec(inp=60, out=40))
            meter.record(
                MeterRecord(kind="tool", name="t", ms=1.0, ts=_ts(2026, 1, 15, 12, 0))
            )  # tool rows are not persisted
            assert meter.tokens_used_today(now=_ts(2026, 1, 15, 13, 0)) == 100
            assert store.tokens_used_today(now=_ts(2026, 1, 15, 13, 0)) == 100
            assert meter.totals()["llm_calls"] == 1
            assert meter.totals()["tool_calls"] == 1
        finally:
            meter.close()

    def test_crosses_utc_midnight_by_record_ts(self, tmp_path) -> None:
        """Rows are bucketed by rec.ts (not call time): yesterday records never count into today."""
        store = MeterStore(tmp_path / "meter.db")
        meter = Meter(store=store)
        try:
            meter.record(_llm_rec(inp=100, ts=_ts(2026, 1, 15, 23, 59)))
            assert meter.tokens_used_today(now=_ts(2026, 1, 16, 8, 0)) == 0
            assert meter.tokens_used_today(now=_ts(2026, 1, 15, 23, 59)) == 100
        finally:
            meter.close()

    def test_store_is_authoritative_no_double_count(self, tmp_path) -> None:
        """With a store present, only the store is read; in-memory records are not added on top (otherwise the same entry would count twice)."""
        store = MeterStore(tmp_path / "meter.db")
        meter = Meter(store=store)
        try:
            meter.record(_llm_rec(inp=30))  # 30 in memory and 30 in the store
            store.add(
                "llm", 100, 0, ts=_ts(2026, 1, 15, 9, 0)
            )  # simulates pre-restart accumulation
            assert meter.tokens_used_today(now=_ts(2026, 1, 15, 10, 0)) == 130
        finally:
            meter.close()


class TestRestartPersistence:
    """Rebuilding build_agent with the same data_dir (simulated restart): usage and quota blocking survive the process boundary."""

    async def test_boot_purges_stale_rows(self, tmp_path) -> None:
        """build_agent startup cleanup: daily rows older than 90 days are purged while building the app; today rows stay."""
        data, ws = tmp_path / "rd", tmp_path / "ws"
        store = MeterStore(data / "meter.db")
        store.add("llm", 100, 0, ts=time.time() - 100 * 86400)  # a row from 100 days ago
        store.add("llm", 12, 6, ts=time.time())  # today
        store.close()
        fake = FakeLLM(default="ok")
        app = build_agent(data_dir=data, workspace_dir=ws, llm=fake)
        try:
            assert app.meter.tokens_used_today() == 18
            stale = time.time() - 100 * 86400
            assert app.meter.tokens_used_today(now=stale) == 0  # the old row is gone from the store
        finally:
            app.close()

    async def test_usage_survives_rebuild(self, tmp_path) -> None:
        data, ws = tmp_path / "rd", tmp_path / "ws"
        fake = FakeLLM(
            dynamic=lambda m, t: LLMReply(text="ok", usage=Usage(input_tokens=12, output_tokens=6))
        )
        app1 = build_agent(data_dir=data, workspace_dir=ws, llm=fake)
        try:
            await app1.master._llm.complete([{"role": "user", "content": "hi"}])
            assert app1.meter.tokens_used_today() == 18
        finally:
            app1.close()
        app2 = build_agent(data_dir=data, workspace_dir=ws, llm=fake)
        try:
            assert app2.meter.tokens_used_today() == 18  # restart does not reset to zero
            quota = await execute(app2.registry, "observe", USER_CTX, {"action": "quota"})
            assert (
                quota["tokens_used_today"] == 18
            )  # the capability reads the same persisted source
        finally:
            app2.close()

    async def test_quota_blocks_after_rebuild(self, tmp_path) -> None:
        """The first process fills the quota; after rebuild, metered_llm still refuses and the underlying LLM is never called."""
        data, ws = tmp_path / "rd", tmp_path / "ws"
        fake = FakeLLM(default="ok")
        app1 = build_agent(data_dir=data, workspace_dir=ws, llm=fake)
        try:
            await app1.settings.set("agent.resource.daily_tokens", 100, LOCAL_USER)
            # ts uses the real clock: after restart, tokens_used_today reads the real "today" from the store
            app1.meter.record(_llm_rec(inp=60, out=40, ts=time.time()))
        finally:
            app1.close()
        app2 = build_agent(data_dir=data, workspace_dir=ws, llm=fake)
        try:
            await app2.settings.set("agent.resource.daily_tokens", 100, LOCAL_USER)
            reply = await app2.master._llm.complete([{"role": "user", "content": "hi"}])
            assert "配额" in (reply.text or "")
            assert len(fake.calls) == 0  # the underlying LLM was never called
        finally:
            app2.close()
