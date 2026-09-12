"""Tests for observability and the daily token quota (resource dimension).

- Meter.tokens_used_today: buckets by UTC calendar day; days are never summed together.
- metered_llm: quota 0 is unlimited, under-limit passes and meters, over-limit refuses
  the real call with degraded text.
- build_agent wiring: the main conversation (direct chat / ReAct instance) LLM goes
  through the wrapper.
"""

import time
from datetime import UTC, datetime

from agent.llm import FakeLLM, LLMReply, Usage
from agent.main import build_agent
from agent.master.arbiter import ArbiterMode
from agent.runtime import (
    Meter,
    MeterRecord,
    is_quota_exceeded_reply,
    metered_llm,
)
from platform_contracts import LOCAL_USER


def _ts(*args: int) -> float:
    """UTC (year, month, day, hour, minute) -> epoch seconds, for pinning moments in tests."""
    y, mo, d, h, mi = args
    return datetime(y, mo, d, h, mi, tzinfo=UTC).timestamp()


def _rec(
    kind: str = "llm",
    name: str = "default",
    ms: float = 1.0,
    inp: int = 0,
    out: int = 0,
    ts: float | None = None,
) -> MeterRecord:
    # Default ts is now: pre-seeded records must fall on "today" to be counted by tokens_used_today
    return MeterRecord(
        kind=kind,
        name=name,
        ms=ms,
        input_tokens=inp,
        output_tokens=out,
        ts=ts if ts is not None else time.time(),
    )


class TestTokensUsedToday:
    def test_sums_same_utc_day(self) -> None:
        meter = Meter()
        meter.record(_rec(inp=100, out=20, ts=_ts(2026, 1, 15, 8, 0)))
        meter.record(_rec(inp=50, ts=_ts(2026, 1, 15, 23, 59)))
        meter.record(_rec(inp=999, ts=_ts(2026, 1, 10, 12, 0)))  # an earlier date
        assert meter.tokens_used_today(now=_ts(2026, 1, 15, 12, 0)) == 170

    def test_crosses_utc_midnight(self) -> None:
        meter = Meter()
        meter.record(_rec(inp=100, ts=_ts(2026, 1, 15, 23, 59)))  # yesterday (UTC)
        meter.record(_rec(inp=40, out=10, ts=_ts(2026, 1, 16, 0, 1)))  # today
        assert meter.tokens_used_today(now=_ts(2026, 1, 16, 8, 0)) == 50
        assert meter.tokens_used_today(now=_ts(2026, 1, 15, 23, 59)) == 100

    def test_empty_meter_is_zero(self) -> None:
        assert Meter().tokens_used_today() == 0


class TestMeteredQuota:
    """metered_llm quota behavior: quota_fn is read hot before each complete; over-limit never touches the underlying LLM."""

    async def test_no_quota_passes_and_meters(self) -> None:
        fake = FakeLLM(default="sure")
        meter = Meter()
        metered = metered_llm(fake, meter)  # no quota_fn = unlimited
        reply = await metered.complete([{"role": "user", "content": "hi"}])
        assert reply.text == "sure"
        assert len(fake.calls) == 1
        assert meter.totals()["llm_calls"] == 1

    async def test_quota_zero_means_unlimited(self) -> None:
        fake = FakeLLM(default="sure")
        meter = Meter()
        metered = metered_llm(fake, meter, quota_fn=lambda: 0)
        reply = await metered.complete([{"role": "user", "content": "hi"}])
        assert reply.text == "sure"
        assert len(fake.calls) == 1

    async def test_under_limit_passes(self) -> None:
        fake = FakeLLM(default="sure")
        meter = Meter()
        meter.record(_rec(inp=50))  # 50 already used today
        metered = metered_llm(fake, meter, quota_fn=lambda: 100)
        reply = await metered.complete([{"role": "user", "content": "hi"}])
        assert reply.text == "sure"
        assert len(fake.calls) == 1

    async def test_over_limit_rejects_before_llm(self) -> None:
        fake = FakeLLM(default="sure")
        meter = Meter()
        meter.record(_rec(inp=60, out=40))  # 100 already used today
        metered = metered_llm(fake, meter, quota_fn=lambda: 100)
        reply = await metered.complete([{"role": "user", "content": "hi"}])
        assert (
            reply.final
        )  # degraded text is delivered as the final reply, not breaking the agent loop
        assert "配额" in (reply.text or "")
        assert len(fake.calls) == 0  # the underlying LLM was never called
        # Only the pre-seeded record is metered; refused calls never enter the meter
        assert meter.totals()["llm_calls"] == 1

    async def test_quota_read_hot_each_call(self) -> None:
        fake = FakeLLM(
            dynamic=lambda m, t: LLMReply(text="ok", usage=Usage(input_tokens=60, output_tokens=40))
        )
        meter = Meter()
        limit = {"v": 0}
        metered = metered_llm(fake, meter, quota_fn=lambda: limit["v"])
        await metered.complete(
            [{"role": "user", "content": "hi"}]
        )  # unlimited: passes and accumulates 100
        limit["v"] = 50  # tightening the limit applies from the very next call
        reply = await metered.complete([{"role": "user", "content": "hi"}])
        assert "配额" in (reply.text or "")
        assert len(fake.calls) == 1


class TestBuildAgentQuota:
    """build_agent wiring: the main conversation (master direct chat / spawner ReAct instance) goes through the wrapper."""

    async def test_master_llm_quota_blocks(self, tmp_path) -> None:
        fake = FakeLLM(
            dynamic=lambda m, t: LLMReply(text="ok", usage=Usage(input_tokens=60, output_tokens=40))
        )
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=fake)
        try:
            await app.settings.set("agent.resource.daily_tokens", 100, LOCAL_USER)
            reply = await app.master._llm.complete([{"role": "user", "content": "hi"}])
            assert reply.text == "ok"  # under limit: passes
            assert len(fake.calls) == 1
            reply = await app.master._llm.complete([{"role": "user", "content": "hi"}])
            assert "配额" in (reply.text or "")  # used 100 >= 100: refused
            assert len(fake.calls) == 1  # the underlying LLM was not called again
        finally:
            app.close()

    async def test_chat_llm_shared_by_master_and_spawner(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            # master (direct-chat branch) and spawner (ReAct instance) receive the same wrapper object
            assert app.master._llm is app.spawner._llm
        finally:
            app.close()

    async def test_default_quota_zero(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            assert app.settings.get("agent.resource.daily_tokens") == 0
        finally:
            app.close()

    async def test_arbiter_and_master_share_metered_llm(self, tmp_path) -> None:
        """The arbitration judge and the master share the chat_llm."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            shared = app.master._llm
            assert app.master._arbiter._llm is shared
            assert app.spawner._llm is shared
        finally:
            app.close()

    async def test_arbiter_quota_blocks_before_llm(self, tmp_path) -> None:
        fake = FakeLLM(default="enqueue")
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=fake)
        try:
            await app.settings.set("agent.resource.daily_tokens", 100, LOCAL_USER)
            app.meter.record(_rec(inp=100))  # today quota already full
            await app.master._arbiter.decide(
                "also check the weather", "write the weekly report", mode=ArbiterMode.AUTO
            )
            assert len(fake.calls) == 0
        finally:
            app.close()


class TestQuotaReplyDetection:
    """is_quota_exceeded_reply: recognizes metered_llm degraded replies."""

    def test_matches_degradation_text(self) -> None:
        assert is_quota_exceeded_reply(
            "（今日 LLM token 配额已用完:明天自动恢复,或在设置里调高/关闭日配额。）"
        )

    def test_normal_text_not_matched(self) -> None:
        assert not is_quota_exceeded_reply("hi there, welcome back")
        assert not is_quota_exceeded_reply("")
        assert not is_quota_exceeded_reply(None)
