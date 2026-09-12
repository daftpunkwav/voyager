"""Session goal: one durable completion target per session, persisted in the
session store's meta table, plus the daily round accounting the continuation
driver enforces.

Status lifecycle: active -> done (agent reports) | blocked (agent reports);
paused by the human, or by boot — a restarted process NEVER resumes a goal
on its own (auto-continuation must be re-armed by a person).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

KEY_PREFIX = "goal:"

ACTIVE, PAUSED, DONE, BLOCKED = "active", "paused", "done", "blocked"


@dataclass(frozen=True)
class Goal:
    session: str
    text: str
    status: str
    rounds: int = 0  # continuation rounds spent today
    day: str = ""  # local date the counter belongs to

    def with_status(self, status: str) -> Goal:
        return Goal(self.session, self.text, status, self.rounds, self.day)


def _today() -> str:
    return time.strftime("%Y-%m-%d")


class GoalManager:
    """Load/save goals through the session store's meta table; pure state."""

    def __init__(self, store: Any) -> None:  # SessionStore (meta helpers)
        self._store = store

    def _key(self, session: str) -> str:
        return f"{KEY_PREFIX}{session}"

    def get(self, session: str) -> Goal | None:
        if self._store is None:
            return None
        raw = self._store.get_meta(self._key(session))
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return Goal(
                session=session,
                text=str(data.get("text") or ""),
                status=str(data.get("status") or PAUSED),
                rounds=int(data.get("rounds") or 0),
                day=str(data.get("day") or ""),
            )
        except (json.JSONDecodeError, TypeError):
            return None

    def _save(self, goal: Goal) -> Goal:
        if self._store is not None:
            self._store.set_meta(
                self._key(goal.session),
                json.dumps(
                    {
                        "text": goal.text,
                        "status": goal.status,
                        "rounds": goal.rounds,
                        "day": goal.day,
                    },
                    ensure_ascii=False,
                ),
            )
        return goal

    def create(self, session: str, text: str) -> Goal:
        return self._save(Goal(session=session, text=text, status=ACTIVE, day=_today()))

    def set_status(self, session: str, status: str) -> Goal | None:
        goal = self.get(session)
        if goal is None:
            return None
        return self._save(goal.with_status(status))

    def clear(self, session: str) -> None:
        if self._store is not None:
            self._store.set_meta(self._key(session), "")

    def active_sessions(self) -> list[str]:
        """Sessions whose persisted goal is still 'active' (boot downgrade
        scans this; nothing else iterates goals)."""
        if self._store is None:
            return []
        out = []
        for key, raw in self._store.meta_entries(KEY_PREFIX).items():
            session = key.removeprefix(KEY_PREFIX)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("status") == ACTIVE:
                out.append(session)
        return out

    def downgrade_active_to_paused(self) -> int:
        """Boot fence: active goals can never survive a restart unattended."""
        count = 0
        for session in self.active_sessions():
            goal = self.get(session)
            if goal is not None:
                self._save(goal.with_status(PAUSED))
                count += 1
        return count

    def may_continue(self, session: str, *, max_rounds_per_day: int) -> bool:
        """Admission check for one more continuation round today."""
        goal = self.get(session)
        if goal is None or goal.status != ACTIVE:
            return False
        rounds = goal.rounds if goal.day == _today() else 0
        return rounds < max_rounds_per_day

    def record_round(self, session: str) -> None:
        goal = self.get(session)
        if goal is None:
            return
        rounds = goal.rounds + 1 if goal.day == _today() else 1
        self._save(Goal(goal.session, goal.text, goal.status, rounds, _today()))


__all__ = ["ACTIVE", "BLOCKED", "DONE", "PAUSED", "Goal", "GoalManager"]
