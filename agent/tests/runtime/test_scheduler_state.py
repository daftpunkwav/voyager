"""Tests for scheduling and run state: concurrency caps, timers, and
checkpoint recovery.
"""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from agent.engine.turn import _surrender_reason
from agent.runtime.scheduler import Scheduler
from agent.runtime.state import MAX_STATE_STEPS, CheckpointStore, RunState, RunStatus


class TestScheduler:
    async def test_concurrency_limit(self) -> None:
        scheduler = Scheduler(max_concurrent=1)
        order: list[str] = []
        gate = asyncio.Event()

        async def first() -> None:
            order.append("a-start")
            await gate.wait()
            order.append("a-end")

        async def second() -> None:
            order.append("b")

        t1 = asyncio.create_task(scheduler.run("a", first()))
        await asyncio.sleep(0)  # let a grab the semaphore first
        t2 = asyncio.create_task(scheduler.run("b", second()))
        await asyncio.sleep(0.01)
        assert order == ["a-start"]  # b is blocked by the semaphore
        assert scheduler.active() == ["a"]
        gate.set()
        await asyncio.gather(t1, t2)
        assert order == ["a-start", "a-end", "b"]
        assert scheduler.active() == []

    async def test_timer_fire_and_cancel(self) -> None:
        scheduler = Scheduler()
        fired: list[str] = []

        async def mark() -> None:
            fired.append("x")

        scheduler.call_later(0.02, mark, name="t1")
        tid = scheduler.call_later(60, mark, name="t2")
        assert scheduler.cancel_timer(tid) is True
        assert scheduler.cancel_timer("missing") is False
        await asyncio.sleep(0.06)
        assert fired == ["x"]  # only t1 fires

    async def test_cancel_named_task(self) -> None:
        scheduler = Scheduler()
        started = asyncio.Event()

        async def long() -> None:
            started.set()
            await asyncio.sleep(60)

        task = asyncio.create_task(scheduler.run("job", long()))
        await started.wait()
        assert await scheduler.cancel("job") is True
        await asyncio.sleep(0)
        assert task.cancelled()


class TestCheckpoint:
    def test_roundtrip_and_alive_filter(self, tmp_path) -> None:
        store = CheckpointStore(tmp_path)
        running = RunState(task="index the repo")
        running.status = RunStatus.RUNNING
        running.add_step("llm", "round-1", "round 1")
        store.save(running)
        done = RunState(task="organize notes")
        done.status = RunStatus.COMPLETED
        store.save(done)

        loaded = store.load(running.run_id)
        assert loaded.task == "index the repo"
        assert loaded.status is RunStatus.RUNNING
        assert loaded.steps[0].summary == "round 1"
        alive = store.list_alive()
        assert [s.run_id for s in alive] == [
            running.run_id
        ]  # crash recovery looks at alive runs only
        store.delete(done.run_id)
        assert len(list(tmp_path.glob("*.json"))) == 1

    def test_status_alive_semantics(self) -> None:
        assert RunStatus.RUNNING.alive and RunStatus.WAITING_INPUT.alive
        assert not RunStatus.COMPLETED.alive and not RunStatus.FAILED.alive

    def test_run_id_traversal_rejected(self, tmp_path) -> None:
        """run_id is joined directly into paths: values like ../../ must be rejected so they cannot escape the checkpoints directory."""
        store = CheckpointStore(tmp_path / "checkpoints")
        for bad in ("../../etc/passwd", "a/b", "..", ""):
            with pytest.raises(ValueError, match="invalid run_id"):
                store.load(bad)
            with pytest.raises(ValueError, match="invalid run_id"):
                store.delete(bad)

    def test_list_alive_skips_broken_files(self, tmp_path) -> None:
        """A broken checkpoint (bad JSON / missing field) is skipped without blocking later valid files, and the bad file is kept."""
        store = CheckpointStore(tmp_path)
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        running = RunState(task="index the repo")
        running.status = RunStatus.RUNNING
        running.run_id = "mid-run"  # fixed names pin the scan order: broken (b) first, valid (m) middle, missing-field (z) last
        store.save(running)
        (tmp_path / "zzz-no-status.json").write_text('{"task":"x"}', encoding="utf-8")

        alive = store.list_alive()  # must not raise even with broken files mixed in

        assert [s.run_id for s in alive] == ["mid-run"]
        # Broken files are kept as-is: no unlink, no rewrite
        assert (tmp_path / "broken.json").read_text(encoding="utf-8") == "{not json"
        assert (tmp_path / "zzz-no-status.json").read_text(encoding="utf-8") == '{"task":"x"}'


class TestRunStateStepsCap:
    """MAX_STATE_STEPS trims the resident steps tail: step numbering keeps
    going through next_n (len(steps)+1 would collide after a trim), legacy
    checkpoints backfill the counter from the retained tail, and the engine's
    surrender scan stays correct because it scopes by step.n — not list
    indices, which the trim shifts."""

    def test_add_step_trims_head_and_next_n_stays_monotonic(self) -> None:
        state = RunState(task="t")
        total = MAX_STATE_STEPS + 5
        for i in range(total):
            state.add_step("llm", f"s{i}", "m")
        assert state.next_n == total
        assert len(state.steps) == MAX_STATE_STEPS
        # the head is dropped, order is preserved, ns stay strictly increasing
        assert [s.n for s in state.steps] == list(range(total - MAX_STATE_STEPS + 1, total + 1))
        # numbering continues past the cap instead of colliding with the tail
        assert state.add_step("tool", "extra", "m").n == total + 1
        assert len(state.steps) == MAX_STATE_STEPS

    def test_from_dict_backfills_legacy_next_n_from_retained_tail(self) -> None:
        state = RunState(task="t")
        for i in range(MAX_STATE_STEPS + 3):
            state.add_step("llm", f"s{i}", "m")
        legacy = state.to_dict()
        del legacy["next_n"]  # pre-counter checkpoint shape
        revived = RunState.from_dict(legacy)
        assert revived.next_n == MAX_STATE_STEPS + 3  # backfilled from the tail's max n
        assert revived.steps[0].n == 4  # the trimmed tail survived the round trip
        # numbering resumes after the retained tail instead of colliding with it
        assert revived.add_step("llm", "next", "m").n == MAX_STATE_STEPS + 4

    def test_surrender_scan_scopes_by_step_n_after_trim(self) -> None:
        """The engine's surrender scan must scope by step.n: once the head is
        trimmed, both surrenders sit near the tail's end, so an index-based
        scan would misattribute (or drop) the current turn's reason."""
        state = RunState(task="t")
        for i in range(249):
            state.add_step("llm", f"filler{i}", "m")
        state.add_step(
            "system", "surrender", "", {"reason": "tool_cap"}
        )  # n=250: a previous turn's stamp
        step_base_n = state.steps[-1].n
        state.add_step("llm", "current-round", "m")
        state.add_step(
            "system", "surrender", "", {"reason": "loop_abort"}
        )  # n=252: this turn's stamp
        assert state.steps[0].n == 53  # the head trim actually happened
        inst: Any = SimpleNamespace(state=state)  # the scan only reads state.steps
        assert _surrender_reason(inst, step_base_n) == "loop_abort"
