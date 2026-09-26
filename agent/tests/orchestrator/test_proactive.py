"""Proactive engine: the follow-up chain fires only when the user never
replied after the original outreach, and the persisted job carries the
outreach time as the reply baseline.

Test type: unit (fakes for the master outlet, budget, queue and event log).
"""

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


class TestGreeting:
    async def test_user_online_sends_greeting_and_schedules_followup(self) -> None:
        import time as _time

        engine, replies = _engine([])
        before = _time.time()
        await engine.on_user_online(SimpleNamespace(payload={"session": "s9"}))
        assert replies == [("a gentle nudge", "s9")]
        (job,) = engine._queue.enqueued
        assert job["kind"] == FOLLOWUP_JOB_KIND
        assert job["payload"]["session"] == "s9"
        assert job["payload"]["topic"] == "a gentle nudge"
        assert job["payload"]["followups"] == 1
        assert before <= job["payload"]["after_ts"] <= _time.time()

    async def test_budget_refusal_stays_silent(self) -> None:
        async def complete(_messages):
            raise AssertionError("the LLM must not be called when the budget refuses")

        master = SimpleNamespace(
            reply=lambda *_a, **_k: None,
            _bus=SimpleNamespace(log=_FakeLog([])),
        )
        budget = OutreachBudget(settings=SimpleNamespace(get=lambda key: False))
        engine = ProactiveEngine(
            master=master,
            llm=SimpleNamespace(complete=complete),
            budget=budget,
            settings=SimpleNamespace(get=lambda key: True),
            scheduler=SimpleNamespace(register_job_handler=lambda *a, **k: None),
            queue=_FakeQueue(),
        )
        await engine.on_user_online(SimpleNamespace(payload={"session": "s1"}))
        assert engine._queue.enqueued == []


class TestComposeFailsClosed:
    async def test_empty_reply_sends_nothing(self) -> None:
        engine, replies = _engine([])
        engine._llm = SimpleNamespace(
            complete=lambda _m: _async(SimpleNamespace(text="   ", degraded=False))
        )
        await engine.on_user_online(SimpleNamespace(payload={"session": "s1"}))
        assert replies == [] and engine._queue.enqueued == []

    async def test_degraded_reply_sends_nothing(self) -> None:
        engine, replies = _engine([])
        engine._llm = SimpleNamespace(
            complete=lambda _m: _async(SimpleNamespace(text="quota", degraded=True))
        )
        await engine.on_user_online(SimpleNamespace(payload={"session": "s1"}))
        assert replies == []

    async def test_llm_failure_sends_nothing(self) -> None:
        engine, replies = _engine([])

        async def _boom(_messages):
            raise RuntimeError("provider down")

        engine._llm = SimpleNamespace(complete=_boom)
        await engine.on_user_online(SimpleNamespace(payload={"session": "s1"}))
        assert replies == []


class TestFollowupGates:
    async def test_chain_exhausted_stays_quiet(self) -> None:
        """max 2 touches: the original + one follow-up (followups>=1 in payload)."""
        engine, replies = _engine([])
        await engine._run_followup_job(
            {"session": "s1", "topic": "t", "followups": 1, "after_ts": 0}
        )
        assert replies == []

    async def test_empty_payload_defaults_are_tolerated(self) -> None:
        engine, replies = _engine([])
        await engine._run_followup_job({})
        assert replies and replies[0][1] == ""

    def test_register_handlers_binds_the_followup_executor(self) -> None:
        bound: dict = {}

        def register(kind, handler):
            bound[kind] = handler

        engine, _ = _engine([])
        engine._scheduler = SimpleNamespace(register_job_handler=register)
        engine.register_handlers()
        assert bound[FOLLOWUP_JOB_KIND] == engine._run_followup_job


async def _async(value):
    return value


async def test_log_read_failure_conservatively_stays_quiet() -> None:
    """The event log exploding must not turn into a nudge: the conservative
    assumption per the module contract is 'the user already replied'."""

    class _BrokenLog:
        def latest_seq(self):
            raise RuntimeError("log exploded")

    engine, replies = _engine([])
    engine._master._bus = SimpleNamespace(log=_BrokenLog())
    await engine._run_followup_job({"session": "s1", "topic": "t", "followups": 0, "after_ts": 0})
    assert replies == []


class TestWiringEdges:
    async def test_bind_attaches_the_master_after_construction(self) -> None:
        """The engine is assembled just before the master: bind() must swap in
        the real outlet so a later greeting reaches the session."""
        engine, _stale = _engine([])
        landed: list[tuple[str, str]] = []

        async def reply(text: str, session: str = "") -> None:
            landed.append((text, session))

        engine._master = SimpleNamespace(reply=lambda *_a, **_k: None)  # not yet bound
        engine.bind(SimpleNamespace(reply=reply, _bus=SimpleNamespace(log=_FakeLog([]))))
        await engine.on_user_online(SimpleNamespace(payload={"session": "s1"}))
        assert landed == [("a gentle nudge", "s1")]

    async def test_greeting_without_a_queue_still_replies(self) -> None:
        """queue=None (no durable chain wired): the greeting goes out and no
        follow-up is scheduled."""
        engine, replies = _engine([])
        engine._queue = None
        await engine.on_user_online(SimpleNamespace(payload={"session": "s1"}))
        assert replies == [("a gentle nudge", "s1")]

    async def test_followup_suppressed_by_budget_stays_quiet(self) -> None:
        engine, replies = _engine([])
        engine._budget = OutreachBudget(settings=SimpleNamespace(get=lambda key: False))
        await engine._run_followup_job(
            {"session": "s1", "topic": "t", "followups": 0, "after_ts": 0}
        )
        assert replies == []

    async def test_followup_with_empty_compose_sends_nothing(self) -> None:
        engine, replies = _engine([])

        async def _empty(_messages):
            return SimpleNamespace(text="", degraded=False)

        engine._llm = SimpleNamespace(complete=_empty)
        await engine._run_followup_job(
            {"session": "s1", "topic": "t", "followups": 0, "after_ts": 0}
        )
        assert replies == [] and engine._queue.enqueued == []
