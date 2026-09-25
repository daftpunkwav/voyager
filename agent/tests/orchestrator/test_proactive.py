"""Proactive engine: the follow-up chain fires only when the user never
replied after the original outreach, and the persisted job carries the
outreach time as the reply baseline."""

from __future__ import annotations

import time
from types import SimpleNamespace

from agent.orchestrator.outreach_budget import OutreachBudget
from agent.orchestrator.proactive import FOLLOWUP_JOB_KIND, ProactiveEngine
from platform_contracts import DomainEvent


class _FakeLog:
    def __init__(self, events: list[tuple[int, SimpleNamespace]]) -> None:
        self._events = events

    def latest_seq(self) -> int:
        return max((seq for seq, _ in self._events), default=0)

    def read_before(self, *, before_seq: int, types=None, limit: int = 500):
        return [(seq, e) for seq, e in self._events if seq < before_seq]


class _FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[dict] = []

    def enqueue(self, **kw):
        self.enqueued.append(kw)
        return kw.get("job_id") or f"{kw['kind']}-test"


def _engine(user_events: list[tuple[int, SimpleNamespace]]):
    replies: list[tuple[str, str]] = []

    async def reply(text: str, session: str = "") -> None:
        replies.append((text, session))

    async def complete(messages):
        return SimpleNamespace(text="a gentle nudge", degraded=False)

    master = SimpleNamespace(reply=reply, _bus=SimpleNamespace(log=_FakeLog(user_events)))
    budget = OutreachBudget(settings=SimpleNamespace(get=lambda key: True))
    engine = ProactiveEngine(
        master=master,
        llm=SimpleNamespace(complete=complete),
        budget=budget,
        settings=SimpleNamespace(get=lambda key: True),
        scheduler=SimpleNamespace(register_job_handler=lambda *a, **k: None),
        queue=_FakeQueue(),
    )
    return engine, replies


def _user_event(session: str, ts: float) -> SimpleNamespace:
    return SimpleNamespace(type=DomainEvent.USER_MESSAGE, payload={"session": session}, ts=ts)


async def test_followup_fires_when_user_never_replied() -> None:
    engine, replies = _engine([])  # no user messages at all
    await engine._run_followup_job(
        {"session": "s1", "topic": "hello", "followups": 0, "after_ts": time.time() - 3600}
    )
    assert replies and replies[0][1] == "s1"


async def test_followup_cancelled_by_later_user_message() -> None:
    after = time.time() - 3600
    # The user spoke after the outreach: the chain is moot.
    engine, replies = _engine([(1, _user_event("s1", after + 60))])
    await engine._run_followup_job(
        {"session": "s1", "topic": "hello", "followups": 0, "after_ts": after}
    )
    assert replies == []


async def test_followup_not_cancelled_by_older_user_message() -> None:
    now = time.time()
    # The only user message predates the outreach: still worth one nudge.
    engine, replies = _engine([(1, _user_event("s1", now - 7200))])
    await engine._run_followup_job(
        {"session": "s1", "topic": "hello", "followups": 0, "after_ts": now - 3600}
    )
    assert replies and replies[0][1] == "s1"


async def test_schedule_followup_stamps_outreach_time_as_baseline() -> None:
    engine, _ = _engine([])
    before = time.time()
    engine._schedule_followup("s1", "topic", delay_s=1800.0)
    (job,) = engine._queue.enqueued
    assert job["kind"] == FOLLOWUP_JOB_KIND
    # The baseline is the moment the outreach went out (never the broken 0,
    # which would make any historical user message count as a reply).
    assert before <= job["payload"]["after_ts"] <= time.time()
