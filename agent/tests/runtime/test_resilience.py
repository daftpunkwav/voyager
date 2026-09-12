"""Runtime resilience tests: lagged backfill, task reaping, and breaker
concurrency counting.
"""

import asyncio
import logging

import pytest
from agent.runtime.loop import EventLoop
from agent.runtime.recovery import CircuitBreaker
from agent.runtime.scheduler import Scheduler
from platform_contracts import ActorKind, ActorRef, Event
from platform_eventbus import CursorStore, EventBus, EventLog


def _bus(tmp_path) -> EventBus:
    log = EventLog(tmp_path / "events.db")
    return EventBus(log)


def _event(type_: str, payload: dict | None = None) -> Event:
    return Event(
        type=type_,
        actor=ActorRef(kind=ActorKind.AGENT, id="agent.main"),
        payload=payload or {},
    )


class TestLaggedDrain:
    async def test_runtime_lagged_events_are_replayed(self, tmp_path) -> None:
        """After the push queue overflows and drops events (sub.lagged set), the loop backfills the missing span from the log."""
        bus = _bus(tmp_path)
        cursors = CursorStore(bus.log.conn, bus.log.lock)
        seen: list[str] = []

        async def on_ping(event: Event) -> None:
            seen.append(str(event.payload.get("n")))

        loop = EventLoop(bus, {"ping": on_ping}, cursors=cursors)
        runner = asyncio.create_task(loop.run())
        await asyncio.sleep(0)  # let the loop finish its startup subscription

        # Simulates queue-overflow loss: events are written to the log only, never pushed (bypassing publish notification)
        for n in range(3):
            bus.log.append(_event("ping", {"n": n}))
        await bus.publish(
            _event("ping", {"n": 3})
        )  # wake the loop: processing always reads the log in order

        async def _await_all() -> None:
            while len(seen) < 4:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(_await_all(), timeout=2)
        runner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await runner
        # The 3 dropped events via backfill plus 1 pushed event are all processed
        assert sorted(seen) == ["0", "1", "2", "3"]

    async def test_startup_drain_pages_past_single_limit(self, tmp_path) -> None:
        """Offline backlog beyond a single backfill limit: paged looping until caught up."""
        bus = _bus(tmp_path)
        cursors = CursorStore(bus.log.conn, bus.log.lock)
        # Pre-write 600 events (> read_missed's default limit of 500)
        for n in range(600):
            bus.log.append(_event("ping", {"n": n}))
        seen: list[str] = []

        async def on_ping(event: Event) -> None:
            seen.append(str(event.payload.get("n")))

        loop = EventLoop(bus, {"ping": on_ping}, cursors=cursors)
        await loop._process_pending()
        assert len(seen) == 600
        # The cursor has advanced to the end; another backfill yields nothing
        seen.clear()
        await loop._process_pending()
        assert seen == []


class TestSchedulerResilience:
    async def test_same_name_rerun_keeps_latest_registration(self) -> None:
        """Same-name task reuse: the earlier finisher must not remove the later finisher registration, and cancels target the right task."""
        s = Scheduler(max_concurrent=4)
        first_release = asyncio.Event()
        seen_during_second: list[list[str]] = []

        async def first() -> str:
            await first_release.wait()
            return "old"

        async def second() -> str:
            seen_during_second.append(s.active())
            return "new"

        t1 = asyncio.create_task(s.run("job", first()))
        await asyncio.sleep(0)  # t1 acquires the semaphore and registers
        assert await s.run("job", second()) == "new"  # same name overwrites the registration
        assert seen_during_second == [["job"]]  # registration present while the new task runs
        first_release.set()
        assert await t1 == "old"
        assert s.active() == []  # both finish; registration is cleared correctly

    async def test_timer_exception_is_logged_not_lost(self, caplog) -> None:
        """A timer callback raising: logged, task reaped, no unreaped warning."""
        s = Scheduler()

        async def boom() -> None:
            raise RuntimeError("timer boom")

        with caplog.at_level(logging.ERROR, logger="agent.scheduler"):
            s.call_later(0, boom)
            await asyncio.sleep(0.05)
        assert any("scheduled callback failed" in r.message for r in caplog.records)
        assert s._timers == {}

    async def test_shutdown_cancels_and_awaits_all(self) -> None:
        s = Scheduler()
        finished: list[str] = []

        async def long_job() -> None:
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                finished.append("cancelled")
                raise

        async def runner() -> None:
            try:
                await s.run("job", long_job())
            except asyncio.CancelledError:
                finished.append("runner-saw-cancel")

        t = asyncio.create_task(runner())
        timer_id = s.call_later(30, long_job)
        await asyncio.sleep(0)
        await s.shutdown()
        await t
        assert sorted(finished) == ["cancelled", "runner-saw-cancel"]
        assert s._tasks == {} and s._timers == {}
        assert timer_id  # id semantics unchanged


class TestBreakerConcurrency:
    async def test_concurrent_failures_count_atomically(self) -> None:
        """Concurrent failure counting is not swallowed by interleaved awaits: 3 straight failures open the breaker."""
        breaker = CircuitBreaker(open_after=3, reset_after=30.0)

        async def fail() -> None:
            await asyncio.sleep(0.01)
            raise RuntimeError("x")

        results = await asyncio.gather(
            *(breaker.call(fail) for _ in range(3)), return_exceptions=True
        )
        assert all(isinstance(r, RuntimeError) for r in results)
        assert breaker.open is True

    async def test_open_rejects_then_half_open_after_reset(self) -> None:
        breaker = CircuitBreaker(open_after=1, reset_after=0.05)

        async def fail() -> None:
            raise RuntimeError("x")

        with pytest.raises(RuntimeError):
            await breaker.call(fail)
        with pytest.raises(asyncio.CancelledError if False else Exception) as ei:
            await breaker.call(fail)
        assert type(ei.value).__name__ == "CircuitOpenError"
        await asyncio.sleep(0.06)  # half-open window
        assert breaker.open is False

        async def ok() -> str:
            return "fine"

        assert await breaker.call(ok) == "fine"
        assert breaker.open is False
