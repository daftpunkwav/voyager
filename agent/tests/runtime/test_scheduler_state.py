"""Tests for scheduling and run state: concurrency caps, timers, and
checkpoint recovery.
"""

import asyncio

import pytest
from agent.runtime.scheduler import Scheduler
from agent.runtime.state import CheckpointStore, RunState, RunStatus


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
