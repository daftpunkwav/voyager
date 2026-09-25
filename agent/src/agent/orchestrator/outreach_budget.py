"""Anti-bombing budget for proactive outreach: per-session and daily caps, a
cooldown between messages, quiet hours and a global switch (all settings,
hot-read). The engine asks the budget before every message; a refusal is
recorded, never raised — silence is the safe default.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from platform_contracts import ServiceError

from agent.settings import (
    OUTREACH_COOLDOWN_KEY as COOLDOWN_KEY,
)
from agent.settings import (
    OUTREACH_DAILY_MAX_KEY as DAILY_MAX_KEY,
)
from agent.settings import (
    OUTREACH_ENABLED_KEY as ENABLED_KEY,
)
from agent.settings import (
    OUTREACH_QUIET_KEY as QUIET_KEY,
)
from agent.settings import (
    OUTREACH_SESSION_MAX_KEY as SESSION_MAX_KEY,
)

_DEFAULT_DAILY_MAX = 3
_DEFAULT_SESSION_MAX = 1
_DEFAULT_COOLDOWN_MIN = 120.0
_DEFAULT_QUIET = "23:00-08:00"

_WINDOW = 500  # bounded history; long-running processes stay bounded


@dataclass(frozen=True)
class BudgetDecision:
    allow: bool
    reason: str = ""


def in_quiet_hours(spec: str, now_ts: float) -> bool:
    """Quiet-hours window "HH:MM-HH:MM" (machine-local wall clock); may span
    midnight. Empty/malformed spec = never quiet."""
    try:
        lo_s, _, hi_s = (spec or "").strip().partition("-")
        lo_h, lo_m = (int(x) for x in lo_s.split(":"))
        hi_h, hi_m = (int(x) for x in hi_s.split(":"))
    except ValueError:
        return False
    lt = time.localtime(now_ts)
    cur = lt.tm_hour * 60 + lt.tm_min
    lo, hi = lo_h * 60 + lo_m, hi_h * 60 + hi_m
    if lo <= hi:
        return lo <= cur < hi
    return cur >= lo or cur < hi  # window spans midnight


class OutreachBudget:
    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._sent: deque[tuple[float, str]] = deque(maxlen=_WINDOW)  # (ts, session)

    def _int(self, key: str, fallback: int) -> int:
        try:
            return int(self._settings.get(key))
        except (TypeError, ValueError, ServiceError):  # unregistered key reads NOT_FOUND
            return fallback

    def allow(self, *, session: str, now_ts: float | None = None) -> BudgetDecision:
        try:
            enabled = self._settings.get(ENABLED_KEY)
        except ServiceError:  # unregistered key: engine on, budgets decide
            enabled = True
        if enabled is False:
            return BudgetDecision(False, "outreach disabled (agent.outreach.enabled)")
        now = time.time() if now_ts is None else now_ts
        raw_quiet = self._settings.get(QUIET_KEY)
        quiet = _DEFAULT_QUIET if raw_quiet is None else str(raw_quiet)  # "" = off
        if in_quiet_hours(quiet, now):
            return BudgetDecision(False, f"quiet hours ({quiet})")
        daily_max = self._int(DAILY_MAX_KEY, _DEFAULT_DAILY_MAX)
        if daily_max > 0 and sum(1 for ts, _ in self._sent if ts > now - 86400) >= daily_max:
            return BudgetDecision(False, f"daily cap reached ({daily_max})")
        session_max = self._int(SESSION_MAX_KEY, _DEFAULT_SESSION_MAX)
        if (
            session_max > 0
            and sum(1 for ts, s in self._sent if s == session and ts > now - 86400) >= session_max
        ):
            return BudgetDecision(False, f"session cap reached ({session_max})")
        cooldown = self._int(COOLDOWN_KEY, int(_DEFAULT_COOLDOWN_MIN)) * 60.0
        if cooldown > 0:
            last_to_session = max((ts for ts, s in self._sent if s == session), default=0.0)
            last_any = max((ts for ts, _ in self._sent), default=0.0)
            if last_any and now - last_any < cooldown:
                return BudgetDecision(False, f"global cooldown ({cooldown / 60:.0f} min)")
            if last_to_session and now - last_to_session < cooldown:
                return BudgetDecision(False, f"session cooldown ({cooldown / 60:.0f} min)")
        return BudgetDecision(True)

    def record(self, *, session: str, now_ts: float | None = None) -> None:
        self._sent.append((time.time() if now_ts is None else now_ts, session))


__all__ = ["BudgetDecision", "OutreachBudget", "in_quiet_hours"]
