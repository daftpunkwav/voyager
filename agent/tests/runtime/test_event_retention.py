"""Event-log retention policy: the high-churn display streams are reclaimed
after a day; durable lanes (conversation messages, job final states, note
lifecycle receipts) are never purged.

The retention object lives in agent.build because both assembly roots
construct the shared log; this test pins the policy so a vocabulary change
cannot silently re-open unbounded growth or start deleting durable history.
"""

import time

from agent.build import EVENTS_RETENTION
from platform_contracts import ActorKind, ActorRef, DomainEvent, Event
from platform_eventbus import EventLog, Retention

_Actor = ActorRef(kind=ActorKind.SYSTEM, id="retention-test")


def test_retention_covers_exactly_the_display_streams() -> None:
    assert set(EVENTS_RETENTION.types) == {
        DomainEvent.AGENT_DELTA,
        DomainEvent.AGENT_STEP,
        DomainEvent.TASK_PROGRESS,
    }
    assert EVENTS_RETENTION.max_age_s == 24 * 3600.0


def test_sweep_purges_display_streams_and_keeps_durable_lanes(tmp_path) -> None:
    db = tmp_path / "events.db"
    log = EventLog(db)
    stale_ts = time.time() - 25 * 3600.0
    for event_type in (
        DomainEvent.AGENT_DELTA,
        DomainEvent.AGENT_STEP,
        DomainEvent.TASK_PROGRESS,
        DomainEvent.USER_MESSAGE,
        DomainEvent.TASK_COMPLETED,
        DomainEvent.NOTE_CREATED,
    ):
        log.append(Event(type=event_type, actor=_Actor, payload={}, ts=stale_ts))
    # A fresh step must survive the sweep (it is only the age that purges)
    log.append(Event(type=DomainEvent.AGENT_STEP, actor=_Actor, payload={}))
    log.close()

    swept = EventLog(
        db,
        retention=Retention(types=EVENTS_RETENTION.types, max_age_s=EVENTS_RETENTION.max_age_s),
    )
    try:
        rows = swept.read_after(0)
        fresh = [e.type for _, e in rows if e.ts >= stale_ts + 3600]
        old = {e.type for _, e in rows if e.ts < stale_ts + 3600}
        assert fresh == [DomainEvent.AGENT_STEP]
        # Durable lanes survive at any age; the high-churn display streams
        # (stale delta/step/progress rows) were reclaimed
        assert old == {
            DomainEvent.USER_MESSAGE,
            DomainEvent.TASK_COMPLETED,
            DomainEvent.NOTE_CREATED,
        }
    finally:
        swept.close()
