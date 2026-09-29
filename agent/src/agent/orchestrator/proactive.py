"""Proactive outreach engine: greet the user when they come online,
follow up once on an unanswered outreach, and otherwise stay quiet.

Design constraints:
- fire-and-forget: every message is composed in ONE LLM call and posted to
  the session via the master's reply outlet; nothing stays resident waiting
  (a proactive instance that lingers burns tokens for no one);
- the budget gate runs before every send — anti-bombing policy lives in
  outreach_budget.py, the engine only asks and records;
- follow-ups are a persisted-queue chain (max 2 touches per topic: the
  original + one follow-up); a user reply in the session cancels the chain.

Triggers subscribed by wire: user.online (greeting), and the follow-up jobs
come from the durable queue (kind = "outreach.followup").
"""

from __future__ import annotations

import logging
import time
from typing import Any

from platform_contracts import DomainEvent

from agent.orchestrator.outreach_budget import OutreachBudget
from agent.prompts import P, render

log = logging.getLogger("agent.outreach")

FOLLOWUP_JOB_KIND = "outreach.followup"
_MAX_FOLLOWUPS = 1  # original message + one follow-up

#: Reply check: backwards page size and page budget. after_ts is at most one
#: follow-up delay old (~30 min), so the walk normally stops at the baseline
#: within a page or two; the budget only bounds a pathological log.
_REPLY_PAGE = 200
_REPLY_SCAN_PAGES = 25


class ProactiveEngine:
    def __init__(
        self,
        *,
        master: Any,
        llm: Any,
        budget: OutreachBudget,
        settings: Any,
        scheduler: Any,
        queue: Any,
    ) -> None:
        self._master = master
        self._llm = llm
        self._budget = budget
        self._settings = settings
        self._scheduler = scheduler
        self._queue = queue

    def bind(self, master: Any) -> None:
        """Attach the master after construction (the engine is assembled just
        before it; composition calls bind immediately after)."""
        self._master = master

    def register_handlers(self) -> None:
        """Job executor for the persisted follow-up chain (survives restarts)."""
        self._scheduler.register_job_handler(FOLLOWUP_JOB_KIND, self._run_followup_job)

    async def on_user_online(self, event) -> None:
        """user.online trigger: a short greeting, budget-gated, fire-and-forget."""
        session = str((event.payload or {}).get("session") or "")
        decision = self._budget.allow(session=session)
        if not decision.allow:
            log.info("outreach suppressed: %s", decision.reason)
            return
        text = await self._compose(P.orchestrator.proactive_greeting)
        if not text:
            return
        self._budget.record(session=session)
        await self._master.reply(text, session=session)
        self._schedule_followup(session, text, delay_s=1800.0)

    async def _run_followup_job(self, payload: dict) -> None:
        """Persisted follow-up job: one nudge if the user never replied."""
        session = str(payload.get("session") or "")
        topic = str(payload.get("topic") or "")[:200]
        done = int(payload.get("followups") or 0)
        if done >= _MAX_FOLLOWUPS or self._user_replied_since(
            session, payload.get("after_ts") or 0
        ):
            return  # user answered (or chain exhausted): stay quiet
        decision = self._budget.allow(session=session)
        if not decision.allow:
            log.info("follow-up suppressed: %s", decision.reason)
            return
        text = await self._compose(render(P.orchestrator.proactive_followup, topic=topic))
        if not text:
            return
        self._budget.record(session=session)
        await self._master.reply(text, session=session)

    def _schedule_followup(self, session: str, topic: str, *, delay_s: float) -> None:
        if self._queue is None:
            return
        self._queue.enqueue(
            kind=FOLLOWUP_JOB_KIND,
            payload={
                "session": session,
                "topic": topic,
                # Followups already sent (the handler refuses >= _MAX_FOLLOWUPS):
                # this job IS the first follow-up, so the chain must start at 0 —
                # a 1 here would make the handler drop the only followup it is
                # scheduled to send.
                "followups": 0,
                # Baseline for "did the user reply": the moment this outreach
                # went out. Any user message in the session after it cancels
                # the chain.
                "after_ts": time.time(),
            },
            delay_s=delay_s,
            priority=-1,
        )

    def _user_replied_since(self, session: str, ts: float) -> bool:
        """A user message in the session after ts means the user is back — the
        chain is moot. USER_MESSAGE rows are paged backwards until the baseline
        ts is passed: a fixed latest-50 window would miss the reply whenever
        other sessions logged 50+ user messages since the outreach, and the
        engine would then send an unwanted follow-up. Past the page budget
        without reaching the baseline, the conservative assumption wins
        (already answered); a log read failure keeps the same answer."""
        try:
            log_ = self._master._bus.log  # engine and master share one process
            cursor = log_.latest_seq() + 1
            for _ in range(_REPLY_SCAN_PAGES):
                rows = log_.read_before(
                    before_seq=cursor, types=[DomainEvent.USER_MESSAGE], limit=_REPLY_PAGE
                )
                if not rows:
                    return False  # log head reached, no reply found
                if any(
                    isinstance(e.payload, dict)
                    and str(e.payload.get("session") or "") == session
                    and e.ts > ts
                    for _, e in rows
                ):
                    return True
                if min(e.ts for _, e in rows) <= ts:
                    return False  # baseline reached: everything older predates it
                cursor = rows[0][0]
            return True  # baseline not reached within the budget: cannot tell
        except Exception:  # noqa: BLE001  # cannot tell -> assume replied (stay quiet)
            return True

    async def _compose(self, instruction: str) -> str:
        """One LLM call, no tools, no residency; an empty reply means 'say
        nothing' and a failure stays logged (outreach is best-effort). The
        instruction rides as the system message plus a minimal user turn:
        a message list with no user role is rejected by several providers
        (Anthropic requires the first non-system turn to be user)."""
        try:
            reply = await self._llm.complete(
                [
                    {"role": "system", "content": instruction},
                    {"role": "user", "content": "Write the outreach message now."},
                ]
            )
        except Exception:  # outreach is best-effort, never breaks the caller
            log.warning("outreach compose failed", exc_info=True)
            return ""
        if reply.degraded:
            return ""
        return (reply.text or "").strip()


__all__ = ["FOLLOWUP_JOB_KIND", "ProactiveEngine"]
