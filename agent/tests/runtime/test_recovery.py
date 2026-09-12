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
"""

import asyncio
import contextlib
import os
import sqlite3
import time
from pathlib import Path

import httpx
import pytest
from agent.llm import FakeLLM, ToolCall
from agent.main import build_agent
from agent.memory import EpisodicMemory
from agent.policy import FsPolicy, PolicyEngine
from agent.runtime import EventLoop
from agent.runtime.state import (
    CheckpointStore,
    ResumeSnapshot,
    RunState,
    RunStatus,
    reclaim_alive,
)
from agent.settings import DEFS as AGENT_SETTING_DEFS
from agent.subagent.instance import TaskBook
from agent.subagent.spawn import TERMINAL_INSTANCE_CAP
from agent.tools import AgentTool, Toolbelt, ensure_workdir
from platform_contracts import LOCAL_USER, Event
from platform_eventbus import CursorStore, EventBus, EventLog
from platform_settings import SettingsStore


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
        assert "[工具失败]" in out and "TimeoutError" in out
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

    async def test_spawn_subagent_is_write_never_retried(self, tmp_path) -> None:
        """spawn_subagent has side effects (creates a run instance): marked write, so on failure the
        handler runs once instead of retrying like a read-only tool and spawning twice."""
        from agent.tools.team import spawn_tool

        calls = {"n": 0}

        async def failing_dispatch(*args, **kwargs):
            calls["n"] += 1
            raise RuntimeError("boom")

        tool = spawn_tool(failing_dispatch)["spawn_subagent"]
        assert tool.write is True
        root = ensure_workdir(tmp_path / "ws")
        belt = _belt(root, {"spawn_subagent": tool})
        out = await belt.call(ToolCall("t1", "spawn_subagent", {"goal": "x"}))
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


async def _until(pred, timeout: float = 2.0) -> None:
    """Deterministically wait for a precondition (under the drain model, sleep(0) no longer guarantees completion)."""
    import asyncio as _asyncio

    async def _poll() -> None:
        while not pred():
            await _asyncio.sleep(0.01)

    await _asyncio.wait_for(_poll(), timeout=timeout)


def _event(type_: str) -> Event:
    return Event(type=type_, actor=LOCAL_USER, payload={})


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


class TestReclaim:
    def test_reclaim_marks_running_failed(self, tmp_path) -> None:
        store = CheckpointStore(tmp_path / "cp")
        state = RunState(task="t")
        state.status = RunStatus.RUNNING
        store.save(state)

        out = reclaim_alive(store)

        assert len(out) == 1
        assert store.list_alive() == []
        loaded = store.load(state.run_id)
        assert loaded.status is RunStatus.FAILED
        assert loaded.error == "process restarted, task not recovered"

    def test_reclaim_noop_on_empty_store(self, tmp_path) -> None:
        assert reclaim_alive(CheckpointStore(tmp_path / "cp")) == []

    async def test_build_agent_reclaims_on_boot(self, tmp_path) -> None:
        """build_agent boot semantics: a legacy alive run without a resume snapshot -> FAILED;
        an alive run with a resume snapshot -> PAUSED awaiting recovery, still in list_alive."""
        cp_dir = tmp_path / "rd" / "checkpoints"
        cp_dir.mkdir(parents=True)
        store = CheckpointStore(cp_dir)
        legacy = RunState(task="t")
        legacy.status = RunStatus.RUNNING
        legacy.run_id = "legacy000001"
        store.save(legacy)
        snap = ResumeSnapshot(
            instance_id="inst0001",
            instance_name="scout",
            persona="recon",
            goal="index the repo",
            history=[{"role": "user", "content": "start"}],
        )
        resumable = RunState(
            task=snap.goal,
            run_id="resume00001",
            status=RunStatus.RUNNING,
            resume=snap.to_dict(),
        )
        store.save(resumable)

        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            loaded = store.load(legacy.run_id)
            assert loaded.status is RunStatus.FAILED
            assert loaded.error == "process restarted, task not recovered"
            kept = store.load(resumable.run_id)
            assert kept.status is RunStatus.PAUSED
            assert kept.error == "process restarted, resumable"
            assert {s.run_id for s in store.list_alive()} == {resumable.run_id}
        finally:
            app.memory.close()

    def test_build_agent_skips_broken_checkpoint(self, tmp_path) -> None:
        """Boot assembly survives broken JSON mixed into the checkpoint directory; valid alive runs still get marked failed and the bad file is preserved."""
        cp_dir = tmp_path / "rd" / "checkpoints"
        cp_dir.mkdir(parents=True)
        (cp_dir / "broken.json").write_text("{not json", encoding="utf-8")
        store = CheckpointStore(cp_dir)
        state = RunState(task="t")
        state.status = RunStatus.RUNNING
        store.save(state)

        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            assert store.list_alive() == []
            loaded = store.load(state.run_id)
            assert loaded.status is RunStatus.FAILED
            # The broken file is kept as-is: no unlink, no rewrite
            assert (cp_dir / "broken.json").read_text(encoding="utf-8") == "{not json"
        finally:
            app.memory.close()


class TestCheckpointAtomicWrites:
    """Atomic writes: save goes through tmp + os.replace, so readers always see a whole file."""

    def test_save_is_atomic_and_no_tmp_left(self, tmp_path) -> None:
        """After save the target is valid JSON and no orphan .tmp files remain in the directory."""
        store = CheckpointStore(tmp_path / "cp")
        state = RunState(task="atomic write", status=RunStatus.RUNNING)
        state.add_step("llm", "round-1", "round 1")

        store.save(state)

        loaded = store.load(state.run_id)
        assert loaded.task == "atomic write"
        assert loaded.status is RunStatus.RUNNING
        assert len(loaded.steps) == 1
        leftovers = [p.name for p in (tmp_path / "cp").glob("*.tmp")]
        assert leftovers == []

    def test_save_does_not_truncate_existing_target(self, tmp_path, monkeypatch) -> None:
        """When the target exists, the old file stays intact until replace succeeds: the half-written
        window is confined to the tmp file (monkeypatch fails the first replace; save raises, the
        old JSON stays readable, and a subsequent save overwrites successfully)."""
        import agent.runtime.state as state_mod

        store = CheckpointStore(tmp_path / "cp")
        state = RunState(task="v1", status=RunStatus.RUNNING)
        state.run_id = "atomicsave01"
        store.save(state)

        real_replace = os.replace
        failed = {"n": 0}

        def _flaky_replace(src, dst):
            if failed["n"] == 0 and str(dst).endswith("atomicsave01.json"):
                failed["n"] += 1
                raise OSError("simulated replace failure")
            return real_replace(src, dst)

        monkeypatch.setattr(state_mod.os, "replace", _flaky_replace)
        state.task = "v2"
        with pytest.raises(OSError):  # a replace failure propagates out of save to the caller
            store.save(state)

        loaded = store.load(state.run_id)
        assert loaded.task == "v1"  # the old whole file was not truncated

        monkeypatch.setattr(state_mod.os, "replace", real_replace)
        store.save(state)  # retry succeeds
        assert store.load(state.run_id).task == "v2"

    def test_concurrent_saves_then_load_valid(self, tmp_path) -> None:
        """Concurrent saves for the same run: the target file is always some complete write (load never
        crashes); even when concurrent os.replace occasionally races on Windows, the target is never half-written."""
        from concurrent.futures import ThreadPoolExecutor

        store = CheckpointStore(tmp_path / "cp")
        store.save(RunState(task="v0", status=RunStatus.RUNNING, run_id="concurrent1"))

        def _save(i: int) -> None:
            for _ in range(5):
                st = RunState(task=f"v{i}", status=RunStatus.RUNNING)
                st.run_id = "concurrent1"
                try:
                    store.save(st)
                except OSError:
                    # Concurrent replace on Windows can raise PermissionError:
                    # single-threaded production never hits it; an individual failed save is not a half-written file
                    pass

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(_save, range(50)))

        loaded = store.load("concurrent1")  # must not raise JSONDecodeError
        assert loaded.status is RunStatus.RUNNING
        assert loaded.task.startswith("v")
        # Exactly one target file remains; leftover .tmp files do not affect list_alive (it globs *.json only)
        assert [p.name for p in (tmp_path / "cp").glob("*.json")] == ["concurrent1.json"]
        assert {s.run_id for s in store.list_alive()} == {"concurrent1"}


class TestCheckpointTmpPurge:
    """Startup purge of orphan .tmp files: only save-shaped names, single directory level."""

    def test_purge_tmp_removes_only_orphan_tmp(self, tmp_path) -> None:
        """Deletes `.{run_id}.json.{hex}.tmp` shapes; valid json, unrelated .tmp, and subdirectories are untouched."""
        cp = tmp_path / "cp"
        store = CheckpointStore(cp)
        state = RunState(task="t", status=RunStatus.PAUSED)
        store.save(state)  # atomic write lands cleanly, no residue
        (cp / f".{state.run_id}.json.deadbeef.tmp").write_text("residue1", encoding="utf-8")
        (cp / ".abc123.json.cafe1234.tmp").write_text("residue2", encoding="utf-8")
        (cp / "foo.tmp").write_text("not save-shaped", encoding="utf-8")
        (cp / "broken.json").write_text("{bad", encoding="utf-8")
        sub = cp / "sub"
        sub.mkdir()
        (sub / ".x.json.aaaabbbb.tmp").write_text("subdir not purged", encoding="utf-8")

        removed = store.purge_tmp()

        assert removed == 2
        assert (cp / f"{state.run_id}.json").is_file()  # valid checkpoint untouched
        assert (cp / "broken.json").is_file()  # broken json untouched as well
        assert (cp / "foo.tmp").is_file()  # non-save shapes are not deleted
        assert (sub / ".x.json.aaaabbbb.tmp").is_file()  # no recursion
        assert list(cp.glob(".*.json.*.tmp")) == []

    def test_purge_tmp_noop_on_empty_store(self, tmp_path) -> None:
        assert CheckpointStore(tmp_path / "cp").purge_tmp() == 0

    async def test_build_agent_purges_tmp_on_boot(self, tmp_path) -> None:
        """build_agent purges orphan .tmp files once during assembly without blocking startup."""
        cp_dir = tmp_path / "rd" / "checkpoints"
        cp_dir.mkdir(parents=True)
        (cp_dir / ".orphan000001.json.deadbeef.tmp").write_text("{}", encoding="utf-8")

        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            assert list(cp_dir.glob(".*.json.*.tmp")) == []
        finally:
            app.memory.close()


class TestTerminalInstanceCap:
    """Spawner terminal-instance residency cap: only terminal instances are evicted; alive/PENDING ones stay."""

    @staticmethod
    def _spawn_many(app, n: int, *, status: RunStatus) -> list:
        insts = []
        for i in range(n):
            inst = app.spawner.spawn(TaskBook(goal=f"task{i}"))
            inst.state.status = status
            insts.append(inst)
        return insts

    def test_trim_evicts_oldest_terminal_keeps_alive(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            alive = self._spawn_many(app, 2, status=RunStatus.RUNNING)
            terminal = self._spawn_many(app, TERMINAL_INSTANCE_CAP + 2, status=RunStatus.COMPLETED)
            evicted = app.spawner._trim_terminal_instances()
            assert evicted == [
                i.id for i in terminal[:2]
            ]  # oldest by insertion order evicted first
            assert len(app.spawner.instances) == TERMINAL_INSTANCE_CAP + len(alive)
            assert all(
                i.id in app.spawner.instances for i in alive
            )  # alive instances are never evicted
            assert terminal[-1].id in app.spawner.instances  # newest terminal instance kept
        finally:
            app.memory.close()

    def test_trim_deletes_evicted_checkpoint_files(self, tmp_path) -> None:
        """Eviction is semantic termination: the evicted run's checkpoint file
        is deleted, not just the in-memory registry entry."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            terminal = self._spawn_many(app, TERMINAL_INSTANCE_CAP + 1, status=RunStatus.COMPLETED)
            for inst in terminal:
                app.checkpoints.save(inst.state)
            evicted = app.spawner._trim_terminal_instances()
            assert len(evicted) == 1
            with pytest.raises(FileNotFoundError):
                app.checkpoints.load(evicted[0])
            kept = terminal[-1]  # newest terminal instance stays, checkpoint intact
            assert app.checkpoints.load(kept.state.run_id).run_id == kept.state.run_id
        finally:
            app.memory.close()

    def test_trim_never_touches_pending_or_alive(self, tmp_path) -> None:
        """PENDING instances have not run yet in the scheduler queue and do not count as terminal."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            self._spawn_many(app, 40, status=RunStatus.PENDING)
            alive = self._spawn_many(app, 5, status=RunStatus.WAITING_INPUT)
            assert app.spawner._trim_terminal_instances() == []
            assert len(app.spawner.instances) == 45
            assert all(i.id in app.spawner.instances for i in alive)
        finally:
            app.memory.close()

    async def test_cancel_triggers_trim(self, tmp_path) -> None:
        """Trigger point: once a cancel lands CANCELLED and the cap is exceeded, the oldest terminal instance is evicted."""
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            terminal = self._spawn_many(app, TERMINAL_INSTANCE_CAP, status=RunStatus.COMPLETED)
            (stop,) = self._spawn_many(app, 1, status=RunStatus.RUNNING)
            cancelled = await app.spawner.cancel(stop.id)
            assert cancelled == [stop.id]
            # 33 terminal > 32 cap: the oldest one is evicted
            assert len(app.spawner.instances) == TERMINAL_INSTANCE_CAP
            assert terminal[0].id not in app.spawner.instances
            assert terminal[-1].id in app.spawner.instances
        finally:
            app.memory.close()


class TestBootEpisodicPurge:
    """Boot purges expired episodes per retention, without requiring the user to open settings first."""

    @staticmethod
    def _seed(rd: Path, *, expired: bool) -> None:
        """Seeds two episodes; with expired=True the first one's ts is backdated 365 days."""
        db = rd / "memory" / "episodic.db"
        epi = EpisodicMemory(db)
        epi.log("consider", "long-ago event")
        epi.log("consider", "recent event")
        if expired:
            conn = sqlite3.connect(str(db))
            try:
                conn.execute(
                    "UPDATE episodes SET ts = ? WHERE summary = ?",
                    (time.time() - 365 * 86400, "long-ago event"),
                )
                conn.commit()
            finally:
                conn.close()
        epi.close()

    async def _preset_retention(self, rd: Path, days: int) -> None:
        """Pre-writes retention before build (same database and registration path as build_agent)."""
        store = SettingsStore(rd / "settings.db")
        store.register_fresh(AGENT_SETTING_DEFS)
        await store.set("agent.memory.retention_days", days, LOCAL_USER)
        store.close()

    async def test_boot_purges_expired_episodes(self, tmp_path) -> None:
        """With retention>0, build_agent purges expired episodes during assembly and keeps fresh ones."""
        rd = tmp_path / "rd"
        self._seed(rd, expired=True)
        await self._preset_retention(rd, 30)

        app = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            summaries = [e["summary"] for e in app.memory.episodic.recent()]
            assert "long-ago event" not in summaries
            assert "recent event" in summaries
        finally:
            app.memory.close()

    async def test_boot_purge_zero_retention_is_noop(self, tmp_path) -> None:
        """retention=0 means agent-managed: boot does not purge, expired entries are kept."""
        rd = tmp_path / "rd"
        self._seed(rd, expired=True)
        await self._preset_retention(rd, 0)

        app = build_agent(data_dir=rd, workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            summaries = [e["summary"] for e in app.memory.episodic.recent()]
            assert "long-ago event" in summaries
            assert "recent event" in summaries
        finally:
            app.memory.close()
