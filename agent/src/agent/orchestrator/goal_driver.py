"""Goal continuation driver: reservation-gated continuation rounds for
active session goals, delivered through the durable queue.

Fence semantics (no unattended loops):
- reserve: one queue job per session (job_id upsert dedupes re-arms);
- admit: the job handler re-checks the goal is still active, the daily round
  budget has room, and quiet hours are over — before starting anything;
- checkpoint: the session persists before the turn runs;
- never auto-revive: boot downgrades active goals to paused, so a queued
  continuation found after a restart fails admission and stays quiet.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from agent.orchestrator.goal import ACTIVE, GoalManager
from agent.orchestrator.outreach_budget import in_quiet_hours
from agent.prompts import P, render
from agent.settings import OUTREACH_QUIET_KEY

log = logging.getLogger("agent.goal")

JOB_KIND = "goal.continue"
CONTINUE_DELAY_S = 300.0
MAX_ROUNDS_PER_DAY = 2


class GoalDriver:
    def __init__(
        self,
        master: Any,
        goals: GoalManager,
        queue: Any,
        settings: Any,
        scheduler: Any,
    ) -> None:
        self._master = master
        self._goals = goals
        self._queue = queue
        self._settings = settings
        scheduler.register_job_handler(JOB_KIND, self._run_goal_job, notify="none")

    def maybe_schedule(self, session: str) -> None:
        """Called after a turn on a session: reserve one continuation round
        when the goal is active. Admission happens in the job, not here."""
        goal = self._goals.get(session)
        if self._queue is None or goal is None or goal.status != ACTIVE:
            return
        self._queue.enqueue(
            kind=JOB_KIND,
            payload={"session": session},
            delay_s=CONTINUE_DELAY_S,
            priority=-1,
            job_id=f"goal-{session}",  # upsert: at most one pending round per session
        )

    async def _run_goal_job(self, payload: dict) -> None:
        """Admission fence, then one notice-driven continuation turn."""
        session = str(payload.get("session") or "")
        goal = self._goals.get(session)
        if goal is None or goal.status != ACTIVE:  # paused/done/cleared: stay quiet
            return
        if not self._goals.may_continue(session, max_rounds_per_day=MAX_ROUNDS_PER_DAY):
            log.info("goal continuation round budget reached (session %s)", session)
            return
        quiet = str(self._settings.get(OUTREACH_QUIET_KEY) or "")
        if in_quiet_hours(quiet, time.time()):
            log.info("goal continuation inside quiet hours (session %s)", session)
            return
        # Checkpoint before the turn: the continuation must not run against a
        # session whose persistence lags its live state
        self._master.sessions.persist(session)
        self._goals.record_round(session)

        # Pre-step barrier: the goal state is re-verified when the turn would
        # actually start (after the session lock), not only at job admission -
        # a pause/clear/done landing in between cancels the wakeup instead of
        # running a stale continuation. The daily round budget is NOT
        # re-checked here: this round is already accounted.
        def _still_active() -> bool:
            current = self._goals.get(session)
            return current is not None and current.status == ACTIVE

        await self._master.handle_notice(
            session,
            render(P.orchestrator.goal_resume, goal=goal.text),
            guard=_still_active,
        )


__all__ = ["ACTIVE", "CONTINUE_DELAY_S", "JOB_KIND", "MAX_ROUNDS_PER_DAY", "GoalDriver"]
