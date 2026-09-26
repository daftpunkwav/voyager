"""EventLoop per-pattern resilience: the handler/relay circuit breaker,
static and dynamic subscription changes, and the wait-for-assembly harness."""

import asyncio
import contextlib

import pytest
from agent.runtime import EventLoop
from platform_contracts import LOCAL_USER, Event
from platform_eventbus import CursorStore, EventBus, EventLog


def _event(type_: str) -> Event:
    return Event(type=type_, actor=LOCAL_USER, payload={})


async def _until(pred, timeout: float = 2.0) -> None:
    """Deterministically wait for a precondition (under the drain model, sleep(0) no longer guarantees completion)."""
    import asyncio as _asyncio

    async def _poll() -> None:
        while not pred():
            await _asyncio.sleep(0.01)

    await _asyncio.wait_for(_poll(), timeout=timeout)


@contextlib.asynccontextmanager
async def _running_loop(loop: EventLoop):
    """Starts loop.run() as a task and cancels it on exit (loop.stop does not wake sub.get, so cancel is required).

    Waits until run actually enters the push loop (run() first does a synchronous backfill read,
    then subscribes, then enters the while; create_task plus a single sleep(0) only reaches the
    first await, which does not guarantee assembly).
    """
    task = asyncio.create_task(loop.run())
    for _ in range(100):  # poll until _sub is assembled (pure in-memory, ready in milliseconds)
        if loop._sub is not None:
            break
        await asyncio.sleep(0)
    else:
        raise AssertionError(
            "loop.run() did not assemble the runtime subscription (sub still None)"
        )
    await asyncio.sleep(0)  # ensure run has returned from read_missed and blocks in sub.get
    try:
        yield
    finally:
        loop.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class TestLoopBreaker:
    async def test_consecutive_failures_skip_handler(self, tmp_path) -> None:
        """After 3 consecutive errors from one handler the breaker opens; the 4th event is not delivered and the loop survives."""
        log = EventLog(tmp_path / "events.db")
        calls = {"bad": 0, "good": 0}

        async def bad(_ev: Event) -> None:
            calls["bad"] += 1
            raise RuntimeError("boom")

        async def good(_ev: Event) -> None:
            calls["good"] += 1

        loop = EventLoop(EventBus(log), {"bad.*": bad, "good.*": good})
        for _ in range(3):
            await loop._dispatch(_event("bad.x"))
        assert calls["bad"] == 3
        await loop._dispatch(_event("bad.x"))  # breaker open: skipped, handler not entered
        assert calls["bad"] == 3
        await loop._dispatch(_event("good.y"))  # other patterns unaffected
        assert calls["good"] == 1
        log.close()


class TestLoopSubscribe:
    """Exact subscription: "*" is forbidden, hooks go through relay, subscription = handlers + extra_patterns."""

    async def test_star_in_handlers_rejected(self, tmp_path) -> None:
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        with pytest.raises(ValueError, match="relay"):
            EventLoop(EventBus(log), {"*": noop})
        log.close()

    async def test_star_in_extra_patterns_rejected(self, tmp_path) -> None:
        """A "*" inside extra_patterns is rejected too (otherwise exact subscription would be silently undone); note.* is allowed."""
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        loop = EventLoop(EventBus(log), {"user.message": noop}, extra_patterns=("note.*",))
        assert "note.*" in loop.patterns  # typed wildcards are allowed
        with pytest.raises(ValueError, match="relay"):
            EventLoop(EventBus(log), {"user.message": noop}, extra_patterns=("*",))
        log.close()

    async def test_patterns_dedup_preserve_order(self, tmp_path) -> None:
        """Subscription patterns dedupe preserving order: handler keys first, extra_patterns appended after."""
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        loop = EventLoop(
            EventBus(log),
            {"bad.*": noop, "good.*": noop},
            extra_patterns=("note.created", "bad.*", "note.created"),
        )
        assert loop.patterns == ("bad.*", "good.*", "note.created")
        log.close()

    async def test_relay_breaker_does_not_touch_domain_handler(self, tmp_path) -> None:
        """Once the relay breaker opens after consecutive failures, only the relay is skipped; domain handlers run on and the loop survives."""
        log = EventLog(tmp_path / "events.db")
        calls = {"good": 0, "relay": 0}

        async def good(_ev: Event) -> None:
            calls["good"] += 1

        async def bad_relay(_ev: Event) -> None:
            calls["relay"] += 1
            raise RuntimeError("relay boom")

        loop = EventLoop(EventBus(log), {"good.*": good}, relay=bad_relay)
        for _ in range(
            5
        ):  # the first 3 enter the relay, then the breaker skips; the handler runs every time
            await loop._dispatch(_event("good.x"))
        assert calls["good"] == 5
        assert calls["relay"] == 3  # open_after defaults to 3; no entries after tripping
        log.close()


class TestLoopDynamicSubscribe:
    """Runtime hook event subscriptions can be added and removed dynamically (subscribe on approval,
    withdraw on revoke, no restart).

    EventLoop owns its runtime subscription; `sync_extra_patterns` converges idempotently to
    handlers + extra with no resubscribe gap and no double subscription. Handler domain bindings
    can never be withdrawn.
    """

    async def test_sync_adds_extra_pattern_and_keeps_handlers(self, tmp_path) -> None:
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        loop = EventLoop(EventBus(log), {"user.message": noop}, extra_patterns=())
        assert loop.patterns == ("user.message",)
        loop.sync_extra_patterns(("note.created",))
        assert loop.patterns == ("user.message", "note.created")

    async def test_sync_removes_only_extra_handlers_untouchable(self, tmp_path) -> None:
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        loop = EventLoop(EventBus(log), {"user.message": noop}, extra_patterns=("note.created",))
        loop.sync_extra_patterns(())  # withdraw all extra patterns
        assert loop.patterns == ("user.message",)  # domain bindings cannot be withdrawn
        log.close()

    async def test_sync_rejects_star(self, tmp_path) -> None:
        """The dynamic API enforces the constructor's ban: any pattern containing "*" is rejected."""
        log = EventLog(tmp_path / "events.db")

        async def noop(_ev: Event) -> None:
            return None

        loop = EventLoop(EventBus(log), {"user.message": noop})
        with pytest.raises(ValueError, match="relay"):
            loop.sync_extra_patterns(("*",))
        log.close()

    async def test_run_started_sync_updates_live_sub(self, tmp_path) -> None:
        """After startup, sync updates the live sub directly: events of the new pattern arrive from the next publish, with no resubscribe."""
        log = EventLog(tmp_path / "events.db")
        bus = EventBus(log)
        seen: list[str] = []

        async def noop(ev: Event) -> None:
            seen.append(ev.type)

        loop = EventLoop(bus, {"user.message": noop}, relay=noop)
        async with _running_loop(loop):
            assert loop._sub is not None and loop.patterns == ("user.message",)
            loop.sync_extra_patterns(("note.created",))
            await bus.publish(_event("note.created"))  # new pattern: push delivery should arrive
            await asyncio.sleep(0)
            assert seen == ["note.created"]  # hook domain events are visible via relay
            assert loop.patterns == ("user.message", "note.created")

    async def test_run_started_drop_stops_new_events(self, tmp_path) -> None:
        """Withdrawing after startup: later publishes of that type are no longer pushed (handler unregistered and pattern unsubscribed)."""
        log = EventLog(tmp_path / "events.db")
        bus = EventBus(log)
        seen: list[str] = []

        async def noop(ev: Event) -> None:
            seen.append(ev.type)

        loop = EventLoop(bus, {"user.message": noop}, extra_patterns=("note.created",))
        async with _running_loop(loop):
            loop.sync_extra_patterns(())
            await bus.publish(_event("note.created"))
            await bus.publish(_event("user.message"))
            await asyncio.sleep(0)
            assert seen == ["user.message"]  # the withdrawn note.created no longer enters the loop

    async def test_sync_before_run_affects_boot_subscription(self, tmp_path) -> None:
        """Before startup, sync only updates the snapshot; run() subscribes with the latest patterns (backfill matches push)."""
        log = EventLog(tmp_path / "events.db")
        bus = EventBus(log)
        seen: list[str] = []

        async def noop(ev: Event) -> None:
            seen.append(ev.type)

        loop = EventLoop(
            bus,
            {"user.message": noop},
            cursors=CursorStore(log.conn),
            relay=noop,
        )
        # Publish a note.created first: before run it sits past the cursor, and boot backfill should read it under the latest subscription
        await bus.publish(_event("note.created"))
        loop.sync_extra_patterns(("note.created",))  # dynamic subscribe before run
        async with _running_loop(loop):
            await _until(lambda: len(seen) == 1)
            assert seen == [
                "note.created"
            ]  # backfill uses the latest snapshot types, including dynamic additions (via relay)

    async def test_extra_patterns_snapshot_backfill_disclosed(self, tmp_path) -> None:
        """Disclosure: backfill types come from the startup snapshot; patterns added dynamically after
        run started are delivered via push only.

        Unit-test caveat: an in-process event cannot land in the log after run started, before the
        dynamic subscribe, and still be missed by push — push and subscription are decided in the
        same synchronous segment of the event loop, so that race window does not exist.
        Verified here: events of the same type published before and after a dynamic unsubscribe are
        not double-processed, and post-unsubscribe events do not arrive; events subscribed before
        the sync still pass through the relay exactly once (push once, relay once).
        """
        log = EventLog(tmp_path / "events.db")
        bus = EventBus(log)
        seen: list[str] = []

        # The relay doubles as a generic event sink (domain events go relay -> on_event)
        async def on_activity(ev: Event) -> None:
            seen.append(ev.type)

        loop = EventLoop(
            bus,
            {"user.activity": on_activity},
            cursors=CursorStore(log.conn),
            relay=on_activity,
        )
        loop.sync_extra_patterns(
            ("note.created",)
        )  # subscribe before run (as if approved at startup)
        async with _running_loop(loop):
            # Event 1: the subscribed note.created goes to relay (no domain handler)
            await bus.publish(_event("note.created"))
            await _until(
                lambda: seen == ["note.created"]
            )  # confirm processing before unsubscribing:
            # cursor mode filters by the live snapshot at processing time; unsubscribing earlier
            # would skip the event (same effect as push withdrawal), so the timing must be deterministic
            loop.sync_extra_patterns(())
            # Event 2: published after unsubscribe -> not processed (unsubscribed + read filter excludes the type)
            await bus.publish(_event("note.created"))
            # Event 3: user.activity (domain handler, unaffected by dynamic changes)
            await bus.publish(_event("user.activity"))
            await _until(lambda: len(seen) == 3)
            # Event 1 via relay once; event 2 never enters; event 3 once via relay + once via the domain handler
            assert seen == ["note.created", "user.activity", "user.activity"]
