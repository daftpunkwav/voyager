"""Tests for event streaming: log reads/filters, push subscriptions, catch-up,
cursors.
"""

import time

import pytest
from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import CursorStore, EventBus, EventLog, Retention

AGENT = ActorRef(kind=ActorKind.AGENT, id="agent.main")


def _ev(type_: str, **payload) -> Event:
    return Event(type=type_, actor=AGENT, payload=payload)


@pytest.fixture()
def log(tmp_path):
    lg = EventLog(tmp_path / "events.db")
    yield lg
    lg.close()


class TestEventLog:
    def test_append_assigns_increasing_seq(self, log) -> None:
        s1 = log.append(_ev("a"))
        s2 = log.append(_ev("b"))
        assert s2 > s1

    def test_read_after_with_type_filter(self, log) -> None:
        log.append(_ev("task.progress", n=1))
        log.append(_ev("agent.message", text="hi"))
        rows = log.read_after(types=["task.progress"])
        assert len(rows) == 1
        assert rows[0][1].payload == {"n": 1}

    def test_read_after_glob_types(self, log) -> None:
        """glob filters match subscription semantics: literal 'task.*' catches task.progress."""
        log.append(_ev("task.enqueued", id="t1"))
        log.append(_ev("task.progress", pct=50))
        log.append(_ev("agent.message", text="hi"))
        rows = log.read_after(types=["task.*"])
        assert [e.type for _, e in rows] == ["task.enqueued", "task.progress"]

    def test_read_after_mixed_exact_and_glob(self, log) -> None:
        """Exact types and globs combine as a union, ordered by seq; types
        outside the query set are not returned."""
        log.append(_ev("agent.message", text="a"))
        log.append(_ev("task.progress", pct=1))
        log.append(_ev("user.message", text="b"))
        rows = log.read_after(types=[DomainEvent.AGENT_MESSAGE, "task.*"])
        assert [e.type for _, e in rows] == ["agent.message", "task.progress"]

    def test_read_before_returns_nearest_older_window_ascending(self, log) -> None:
        """Backward paging: with limit < matching rows, read_before returns the
        page immediately before the cursor (not the oldest page), ascending."""
        for i in range(5):
            log.append(_ev("user.message", n=i))
        rows = log.read_before(before_seq=6, limit=2)
        assert [e.payload["n"] for _, e in rows] == [3, 4]
        assert [seq for seq, _ in rows] == [4, 5]

    def test_read_before_cursor_is_exclusive(self, log) -> None:
        """seq == before_seq is excluded, mirroring read_after's seq > after_seq."""
        s1 = log.append(_ev("user.message", n=1))
        log.append(_ev("user.message", n=2))
        rows = log.read_before(before_seq=s1 + 1, limit=10)
        assert [e.payload["n"] for _, e in rows] == [1]

    def test_read_before_type_filters(self, log) -> None:
        """Type filters (exact + glob) apply to backward reads with the same
        subscription semantics as forward reads."""
        log.append(_ev("task.progress", n=1))
        log.append(_ev("agent.message", text="hi"))
        log.append(_ev("task.progress", n=2))
        log.append(_ev("user.message", n=3))
        rows = log.read_before(before_seq=5, types=["task.*"], limit=1)
        assert [e.payload["n"] for _, e in rows] == [2]
        rows = log.read_before(before_seq=5, types=["agent.message", "task.*"], limit=10)
        assert [e.type for _, e in rows] == ["task.progress", "agent.message", "task.progress"]

    def test_read_before_empty_range(self, log) -> None:
        log.append(_ev("user.message", n=1))
        assert log.read_before(before_seq=1) == []
        assert log.read_before(before_seq=0) == []

    def test_roundtrip_preserves_fields(self, log) -> None:
        ev = _ev("user.message", text="hello")
        log.append(ev)
        restored = log.read_after()[0][1]
        assert restored.id == ev.id
        assert restored.actor == AGENT
        assert restored.payload == {"text": "hello"}

    def test_cross_instance_shared_db(self, tmp_path) -> None:
        """Two processes (instances) share one db: one writes, the other reads via cursor."""
        path = tmp_path / "events.db"
        writer = EventLog(path)
        writer.append(_ev("graph.indexed", repo="x"))
        reader = EventLog(path)
        assert [e.type for _, e in reader.read_after()] == ["graph.indexed"]
        writer.close()
        reader.close()


class TestRetention:
    """High-churn type retention: purge deletes only the given types older
    than the cutoff; sweeps run at construction and every sweep_every
    appends; message-level events are never touched."""

    def test_purge_deletes_only_matching_type_and_age(self, tmp_path) -> None:
        lg = EventLog(tmp_path / "events.db")
        try:
            old = time.time() - 10_000
            lg.append(Event(type="agent.delta", actor=AGENT, payload={"n": 1}, ts=old))
            lg.append(Event(type="agent.message", actor=AGENT, payload={"n": 2}, ts=old))
            lg.append(Event(type="agent.delta", actor=AGENT, payload={"n": 3}))  # fresh
            deleted = lg.purge(["agent.delta"], before_ts=time.time() - 5_000)
            assert deleted == 1
            rows = lg.read_after()
            assert sorted(e.type for _, e in rows) == ["agent.delta", "agent.message"]
        finally:
            lg.close()

    def test_construction_sweep_removes_stale_deltas(self, tmp_path) -> None:
        lg = EventLog(tmp_path / "events.db")
        lg.append(Event(type="agent.delta", actor=AGENT, payload={}, ts=time.time() - 10_000))
        lg.append(Event(type="agent.message", actor=AGENT, payload={}, ts=time.time() - 10_000))
        lg.close()
        lg2 = EventLog(
            tmp_path / "events.db",
            retention=Retention(types=("agent.delta",), max_age_s=5_000),
        )
        try:
            rows = lg2.read_after()
            assert [e.type for _, e in rows] == ["agent.message"]
        finally:
            lg2.close()

    def test_append_triggers_sweep_every_n(self, tmp_path) -> None:
        lg = EventLog(
            tmp_path / "events.db",
            retention=Retention(types=("agent.delta",), max_age_s=1.0, sweep_every=2),
        )
        try:
            lg.append(Event(type="agent.delta", actor=AGENT, payload={}, ts=time.time() - 10))
            assert len(lg.read_after()) == 1  # sweep runs on multiples of 2 only
            lg.append(Event(type="agent.message", actor=AGENT, payload={}))
            rows = lg.read_after()
            assert [e.type for _, e in rows] == ["agent.message"]  # stale delta swept
        finally:
            lg.close()


class TestCursorStore:
    def test_default_zero_and_roundtrip(self, log) -> None:
        cs = CursorStore(log.conn)
        assert cs.get("graph.worker") == 0
        cs.set("graph.worker", 42)
        assert cs.get("graph.worker") == 42


class TestEventBus:
    async def test_publish_pushes_to_matching_subscriber(self, log) -> None:
        bus = EventBus(log)
        sub = bus.subscribe("task.*")
        other = bus.subscribe("user.*")
        ev = _ev("task.progress", n=1)
        await bus.publish(ev)
        assert (await sub.get(timeout=1)) is ev
        assert other.queue.empty()

    async def test_event_persisted_before_push(self, log) -> None:
        bus = EventBus(log)
        await bus.publish(_ev(DomainEvent.AGENT_MESSAGE, text="hi"))
        assert bus.replay()[0][1].type == "agent.message"

    async def test_slow_subscriber_lagged_then_catches_up(self, log) -> None:
        bus = EventBus(log, queue_size=1)
        sub = bus.subscribe("*")
        await bus.publish(_ev("a"))
        await bus.publish(_ev("b"))  # queue full: push dropped, event is already in the log
        assert sub.lagged
        missed = bus.read_missed("sub-1", CursorStore(log.conn))
        assert [e.type for _, e in missed] == ["a", "b"]

    async def test_cursor_not_advanced_when_idle(self, log) -> None:
        bus = EventBus(log)
        await bus.publish(_ev("a"))
        cs = CursorStore(log.conn)
        bus.read_missed("sub-1", cs)
        assert bus.read_missed("sub-1", cs) == []  # already consumed, not re-delivered
        assert cs.get("sub-1") == 1

    async def test_unsubscribe(self, log) -> None:
        bus = EventBus(log)
        sub = bus.subscribe("*")
        bus.unsubscribe(sub)
        await bus.publish(_ev("a"))
        assert sub.queue.empty()


class TestSubscriptionDynamic:
    """Dynamic pattern add/drop at runtime, reflected immediately in matches
    without resubscribing (foundation for the agent's dynamic subscriptions)."""

    async def test_add_patterns_makes_publish_match(self, log) -> None:
        bus = EventBus(log)
        sub = bus.subscribe("task.progress")
        assert not sub.matches("task.enqueued")
        sub.add_patterns("task.enqueued")
        assert sub.matches("task.enqueued")  # matches updates immediately
        assert sub.patterns == ("task.progress", "task.enqueued")  # insertion order preserved
        await bus.publish(_ev("task.enqueued", id="t1"))
        assert (await sub.get(timeout=1)).payload == {"id": "t1"}  # push arrives immediately

    async def test_drop_patterns_stops_matching(self, log) -> None:
        bus = EventBus(log)
        sub = bus.subscribe("task.progress", "task.enqueued")
        sub.drop_patterns("task.progress")
        assert not sub.matches("task.progress")
        assert sub.patterns == ("task.enqueued",)
        await bus.publish(_ev("task.progress", pct=1))  # dropped: no longer subscribed
        await bus.publish(_ev("task.enqueued", id="t2"))
        assert (await sub.get(timeout=1)).payload == {"id": "t2"}
        assert sub.queue.empty()

    async def test_add_duplicate_and_missing_drop_noop(self, log) -> None:
        sub = EventBus(log).subscribe("a")
        sub.add_patterns("a")  # duplicates are deduplicated
        sub.drop_patterns("ghost")  # dropping an absent pattern is a no-op
        assert sub.patterns == ("a",)

    async def test_already_queued_event_not_retracted_by_drop(self, log) -> None:
        """Events already pushed against the enqueue-time patterns are not
        affected by a later drop (no double-delete, no loss)."""
        bus = EventBus(log)
        sub = bus.subscribe("a")
        await bus.publish(_ev("a", n=1))  # matched at enqueue time
        sub.drop_patterns("a")  # unsubscribed afterwards
        assert (await sub.get(timeout=1)).payload == {"n": 1}  # queued event still deliverable

    async def test_unsubscribe_removes_from_subs(self, log) -> None:
        """After unsubscribe, _subs no longer contains the subscription and
        add/drop become no-ops on it."""
        bus = EventBus(log)
        sub = bus.subscribe("a")
        bus.unsubscribe(sub)
        assert sub not in bus._subs
        sub.add_patterns("b")
        await bus.publish(_ev("b"))
        assert sub.queue.empty()
