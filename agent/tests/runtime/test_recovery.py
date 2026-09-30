"""Resilience wiring tests: tool retry/breaker, EventLoop per-pattern breaker,
checkpoint reclaim.

- Read-only tools retry until success; write tools stop after one failure (prevents
  double writes).
- Timeouts are not retried; the breaker is per tool name and counts every handler
  attempt, and an open breaker stops entering the handler.
- An EventLoop pattern failing consecutively is skipped; other patterns are unaffected
  and the loop survives.
- On boot, alive checkpoints without a resume snapshot are marked failed; ones with a
  snapshot become PAUSED awaiting recovery.
- The breaker's half-open state admits a single probe; concurrent callers fail fast.
"""

import asyncio

import httpx
import pytest
from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.runtime.recovery import CircuitBreaker, CircuitOpenError
from agent.tools import AgentTool, Toolbelt, ensure_workdir


def _flaky_tool(fails: int, counter: dict, *, write: bool = False) -> AgentTool:
    """Raises for the first fails calls, then succeeds; dimension=none passes policy L0."""

    async def handler(**kwargs) -> str:
        counter["calls"] += 1
        if counter["calls"] <= fails:
            raise RuntimeError("boom")
        return "ok"

    return AgentTool(
        name="flaky",
        description="flaky tool for tests",
        handler=handler,
        dimension="none",
        write=write,
    )


def _belt(root, tools: dict[str, AgentTool]) -> Toolbelt:
    # backoff=0: unit tests never actually sleep (0.1s x n)
    return Toolbelt(tools, PolicyEngine(fs=FsPolicy(roots=(str(root),))), retry_backoff=0)


class TestToolRetry:
    async def test_read_only_tool_retries_then_succeeds(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}
        belt = _belt(root, {"flaky": _flaky_tool(2, counter)})
        out = await belt.call(ToolCall("1", "flaky", {}))
        assert out == "ok"
        assert counter["calls"] == 3  # first attempt + 2 retries

    async def test_write_tool_never_retries(self, tmp_path) -> None:
        """Write tools stop after a single failure: retrying would double-write or delete twice."""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}
        belt = _belt(root, {"flaky": _flaky_tool(1, counter, write=True)})
        out = await belt.call(ToolCall("1", "flaky", {}))
        assert "[工具失败]" in out
        assert counter["calls"] == 1

    async def test_timeout_not_retried(self, tmp_path) -> None:
        """Timeouts are not retried by default: MCP/shell timeout x backoff retries only drags on;
        even a read-only tool raising TimeoutError enters the handler once, failing on the first timeout."""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}

        async def slow(**kwargs) -> str:
            counter["calls"] += 1
            raise TimeoutError("upstream did not respond within 30s")

        belt = _belt(
            root,
            {
                "slow": AgentTool(
                    name="slow",
                    description="timeout tool for tests",
                    handler=slow,
                    dimension="none",
                )
            },
        )
        out = await belt.call(ToolCall("1", "slow", {}))
        assert out.startswith("[超时] slow 在")  # friendly wording, no retry
        assert counter["calls"] == 1

    async def test_httpx_timeout_not_retried(self, tmp_path) -> None:
        """URL-based MCP timeouts are not retried: session.py's httpx.AsyncClient raises
        httpx.TimeoutException, matching stdio MCP (built-in TimeoutError); the handler runs once
        and the failure goes straight to the breaker / failure text."""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}

        async def slow(**kwargs) -> str:
            counter["calls"] += 1
            raise httpx.TimeoutException("timed out")

        belt = _belt(
            root,
            {
                "slow": AgentTool(
                    name="slow",
                    description="URL MCP timeout tool for tests",
                    handler=slow,
                    dimension="none",
                )
            },
        )
        out = await belt.call(ToolCall("1", "slow", {}))
        assert "[工具失败]" in out and "TimeoutException" in out
        assert counter["calls"] == 1

    async def test_subagent_spawn_is_write_never_retried(self, tmp_path) -> None:
        """subagent(action=spawn) has side effects (creates a run instance): marked write, so on
        failure the handler runs once instead of retrying like a read-only tool and spawning twice."""
        from agent.tools.team import subagent_tool
        from platform_capability import Registry, capability

        calls = {"n": 0}
        reg = Registry("agent")

        @capability(reg, name="subagent", description="x")
        async def subagent(action: str = "spawn", goal: str = "") -> dict:
            calls["n"] += 1
            raise RuntimeError("boom")

        tool = subagent_tool(reg)
        assert tool.write is True
        root = ensure_workdir(tmp_path / "ws")
        belt = _belt(root, {"subagent": tool})
        out = await belt.call(ToolCall("t1", "subagent", {"action": "spawn", "goal": "x"}))
        assert "[工具失败]" in out
        assert calls["n"] == 1


class TestToolBreaker:
    async def test_opens_after_consecutive_failures(self, tmp_path) -> None:
        """Three consecutive handler failures (default open_after) open the breaker; every attempt
        within retries counts toward it, and once open the handler is not entered again."""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}
        belt = _belt(root, {"flaky": _flaky_tool(10**9, counter)})
        # All 3 handler attempts inside a single belt.call fail -> the breaker opens immediately
        assert "[工具失败]" in await belt.call(ToolCall("1", "flaky", {}))
        assert counter["calls"] == 3
        assert "[熔断]" in await belt.call(
            ToolCall("2", "flaky", {})
        )  # later calls short-circuit at the breaker
        assert counter["calls"] == 3  # handler not entered once open

    async def test_breaker_shared_across_trimmed_views(self, tmp_path) -> None:
        """Trimmed views share the breaker with the root roster: rebuilding a view does not reset it."""
        root = ensure_workdir(tmp_path / "ws")
        counter = {"calls": 0}
        belt = _belt(root, {"flaky": _flaky_tool(10**9, counter)})
        await belt.call(ToolCall("1", "flaky", {}))  # 3 handler failures open the breaker
        trimmed = belt.trimmed(["flaky"])
        assert "[熔断]" in await trimmed.call(ToolCall("2", "flaky", {}))
        assert counter["calls"] == 3


class TestCircuitBreakerHalfOpen:
    async def test_half_open_admits_single_probe(self) -> None:
        """After reset_after only the first call enters fn; a concurrent caller
        fails fast with CircuitOpenError until the probe resolves."""
        cb = CircuitBreaker(open_after=1, reset_after=0.05)

        async def boom() -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await cb.call(boom)
        assert cb.open is True
        await asyncio.sleep(0.06)  # half-open now

        entered = asyncio.Event()
        release = asyncio.Event()

        async def probe() -> str:
            entered.set()
            await release.wait()
            return "ok"

        first = asyncio.create_task(cb.call(probe))
        await entered.wait()  # the probe holds the half-open slot
        with pytest.raises(CircuitOpenError):
            await cb.call(probe)  # second concurrent caller: rejected, fn not entered
        release.set()
        assert await first == "ok"
        assert cb.open is False  # probe success closed the breaker

    async def test_failed_probe_reopens(self) -> None:
        """A failed half-open probe re-opens the circuit for another window."""
        cb = CircuitBreaker(open_after=1, reset_after=0.05)

        async def boom() -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await cb.call(boom)
        await asyncio.sleep(0.06)
        with pytest.raises(RuntimeError):
            await cb.call(boom)  # the probe itself failed
        assert cb.open is True
        # Still within the new window: closed again for everyone
        with pytest.raises(CircuitOpenError):
            await cb.call(boom)

    async def test_cancelled_probe_releases_the_half_open_slot(self) -> None:
        """A cancelled probe must release the probe slot without counting a
        failure: otherwise the breaker stays wedged in "probe in flight"
        forever and never recovers."""
        cb = CircuitBreaker(open_after=1, reset_after=0.05)

        async def boom() -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await cb.call(boom)
        assert cb.open is True
        await asyncio.sleep(0.06)  # half-open now

        entered = asyncio.Event()

        async def slow() -> None:
            entered.set()
            await asyncio.sleep(60)

        probe = asyncio.create_task(cb.call(slow))
        await entered.wait()  # the probe holds the half-open slot
        probe.cancel()
        with pytest.raises(asyncio.CancelledError):
            await probe

        # The slot is free again: the next half-open caller enters fn (and its
        # failure re-opens the circuit instead of being rejected up front).
        with pytest.raises(RuntimeError, match="boom"):
            await cb.call(boom)
        assert cb.open is True
