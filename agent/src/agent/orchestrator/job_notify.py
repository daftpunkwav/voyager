"""Background-job completion notifier: turns scheduler events into either a
quiet notice (assistant-side message) or a wakeup (a notice-driven turn),
gated by the anti-self-excitation budget.

Delivery vocabulary lives here, not in the scheduler: the scheduler reports
(kind, ok, error, pref) and stays free of session/master concepts.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.orchestrator.wake_budget import WakeBudget

log = logging.getLogger("agent.jobs.notify")

_QUIET_MAX_CHARS = 300


class JobNotifier:
    """Listener installed as the scheduler's completion callback."""

    def __init__(self, master: Any, budget: WakeBudget) -> None:
        self._master = master
        self._budget = budget

    async def __call__(self, job: Any, ok: bool, error: str, pref: str) -> None:
        payload = dict(job.payload or {})
        session = str(payload.get("session") or "")
        if not session:
            session = self._master.sessions.active_id()
        head = f"[后台任务] {job.kind}({job.id})" + ("完成" if ok else "失败")
        detail = "" if ok else f":{error[:_QUIET_MAX_CHARS]}"
        text = f"{head}{detail}"
        if pref == "quiet":
            await self._master.reply(text, session=session)
            return
        # wakeup: degrade to a quiet notice once the consecutive-wake budget
        # is exhausted (the chain must not feed itself)
        if self._budget.allow(session):
            self._budget.record(session)
            await self._master.handle_notice(session, text)
            return
        log.info("wakeup suppressed by wake budget (session %s)", session)
        await self._master.reply(text, session=session)


__all__ = ["JobNotifier"]
