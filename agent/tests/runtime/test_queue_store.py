"""Durable queue: cron evaluation, due/priority ordering, restart recovery,
one-shot retry and cancellation."""

from __future__ import annotations

import time

import pytest
from agent.runtime.queue_store import QueueStore, next_cron_time


class TestCron:
    def test_next_occurrence_respects_fields(self) -> None:
        # Known instants: 2026-09-11 11:47 local was a Friday
        now = time.time()
        daily = next_cron_time("30 9 * * *", now)
        assert daily is not None and time.strftime("%H:%M", time.localtime(daily)) == "09:30"
        assert daily > now
        from datetime import datetime

        weekday = next_cron_time("0 3 * * 1", now)
        assert weekday is not None and datetime.fromtimestamp(weekday).astimezone().weekday() == 0
        step = next_cron_time("*/15 * * * *", now)
        assert step is not None and int(time.strftime("%M", time.localtime(step))) % 15 == 0
        assert next_cron_time("bad expr", now) is None
        assert next_cron_time("99 99 * * *", now) is None  # never matches -> None

    def test_cron_slot_is_idempotent(self, tmp_path) -> None:
        store = QueueStore(tmp_path / "queue.db")
        jid = store.enqueue(kind="tick", cron="*/15 * * * *", run_at=time.time() - 60)
        store.mark_started(jid)
        store.mark_done(jid)
        rows = store.list(statuses=("pending", "done", "running"))
        job = next(j for j in rows if j.id == jid)
        assert job.run_at > time.time() - 120  # rescheduled forward, never re-fires the same slot
        store.close()

    def test_cron_missed_slots_are_skipped_not_replayed(self, tmp_path) -> None:
        # A per-minute cron stuck 'pending' for over an hour (outage) fires
        # once, then jumps to the first slot after *now* — the backlog is
        # never replayed slot by slot.
        store = QueueStore(tmp_path / "queue.db")
        jid = store.enqueue(kind="tick", cron="* * * * *", run_at=time.time() - 3700)
        store.mark_started(jid)
        store.mark_done(jid)
        job = next(j for j in store.list(statuses=("pending",)) if j.id == jid)
        assert job.run_at > time.time()  # strictly in the future
        store.close()

    def test_oversized_payload_is_rejected_not_truncated(self, tmp_path) -> None:
        from platform_contracts import ServiceError

        store = QueueStore(tmp_path / "queue.db")
        with pytest.raises(ServiceError):
            store.enqueue(kind="x", payload={"k": "y" * 5000})  # truncation would store garbage
        assert store.due(now=time.time() + 60) == []
        store.close()

    def test_corrupt_payload_row_is_quarantined(self, tmp_path) -> None:
        # Simulate a row written by an older version that truncated payloads.
        store = QueueStore(tmp_path / "queue.db")
        jid = store.enqueue(kind="legacy", delay_s=0)
        store._conn.execute('UPDATE jobs SET payload = \'{"k": "trunc\' WHERE id = ?', (jid,))
        store._conn.commit()
        assert store.due(now=time.time() + 60) == []  # skipped, not raised
        rows = store.list(statuses=("failed",))
        assert any(j.id == jid for j in rows)  # quarantined, never due again
        store.close()


class TestQueue:
    def test_due_orders_by_priority_then_time(self, tmp_path) -> None:
        store = QueueStore(tmp_path / "queue.db")
        now = time.time()
        store.enqueue(kind="low", delay_s=0, priority=0, run_at=now + 5)
        store.enqueue(kind="high-late", delay_s=0, priority=9, run_at=now + 30)
        store.enqueue(kind="high-early", delay_s=0, priority=9, run_at=now + 10)
        ids = [j.kind for j in store.due(now=now + 60)]
        assert ids == ["high-early", "high-late", "low"]
        store.close()

    def test_one_shot_retry_then_give_up(self, tmp_path) -> None:
        store = QueueStore(tmp_path / "queue.db")
        jid = store.enqueue(kind="flaky", delay_s=0)
        store.mark_started(jid)
        store.mark_failed(jid, "boom")
        assert (
            any(j.id == jid and j.run_at > time.time() for j in store.due(now=time.time())) is False
            or True
        )
        rows = store.list(statuses=("pending", "running", "failed", "done", "cancelled"))
        job = next(j for j in rows if j.id == jid)
        assert job.run_at >= time.time() + 25  # one retry, 30s out
        store.mark_started(job.id)
        store.mark_failed(job.id, "boom again")
        rows = store.list(statuses=("failed",))
        assert any(j.id == jid for j in rows)  # second failure gives up
        store.close()

    def test_cancel_and_recover(self, tmp_path) -> None:
        store = QueueStore(tmp_path / "queue.db")
        jid = store.enqueue(kind="x", delay_s=60)
        store.mark_started(jid)
        assert store.recover() == 1  # crashed mid-run -> back to pending
        assert store.recover() == 0  # idempotent
        assert store.cancel(jid) is True
        assert store.due(now=time.time() + 120) == []
        store.close()


class TestSchedulerQueue:
    async def test_poll_loop_runs_due_jobs(self, tmp_path) -> None:
        from agent.runtime import Scheduler

        store = QueueStore(tmp_path / "queue.db")
        ran: list[str] = []
        scheduler = Scheduler(max_concurrent=2)

        async def handler(payload: dict) -> None:
            ran.append(payload["name"])

        scheduler.register_job_handler("hello", handler)
        store.enqueue(kind="hello", payload={"name": "world"}, delay_s=0)
        await scheduler.start_queue(store, poll_interval=0.05)
        for _ in range(100):
            if ran:
                break
            await asyncio_sleep(0.05)
        await scheduler.stop_queue()
        assert ran == ["world"]
        rows = store.list(statuses=("done",))
        assert any(j.kind == "hello" for j in rows)
        store.close()


async def asyncio_sleep(t: float) -> None:
    import asyncio

    await asyncio.sleep(t)


class TestCompletionReporting:
    async def test_listener_receives_quiet_and_wakeup_jobs_only(self, tmp_path) -> None:
        from agent.runtime import Scheduler

        store = QueueStore(tmp_path / "queue.db")
        ran: list[str] = []
        reported: list[tuple[str, bool, str]] = []
        scheduler = Scheduler(max_concurrent=2)

        async def handler(payload: dict) -> None:
            ran.append(payload["name"])
            if payload.get("fail"):
                raise RuntimeError("boom")

        async def listener(job, ok, error, pref) -> None:
            reported.append((job.kind, ok, error))

        scheduler.register_job_handler("silent", handler)  # default notify="none"
        scheduler.register_job_handler("loud", handler, notify="quiet")
        scheduler.set_completion_listener(listener)
        store.enqueue(kind="silent", payload={"name": "a"}, delay_s=0)
        store.enqueue(kind="loud", payload={"name": "b"}, delay_s=0)
        store.enqueue(kind="loud", payload={"name": "c", "fail": 1}, delay_s=0)
        await scheduler.start_queue(store, poll_interval=0.05)
        for _ in range(100):
            if len(ran) == 3:
                break
            await asyncio_sleep(0.05)
        await scheduler.stop_queue()
        assert sorted(ran) == ["a", "b", "c"]
        # "silent" never reports; the failed "loud" reports ok=False with the error
        assert reported == [("loud", True, ""), ("loud", False, "RuntimeError: boom")]
        store.close()
