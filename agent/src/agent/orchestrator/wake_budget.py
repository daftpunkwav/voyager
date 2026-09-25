"""Anti-self-excitation budget for background-task wakeups.

A wakeup is a background completion that starts an agent turn. If that turn
starts another background task, whose completion wakes another turn, the
loop feeds itself: after `max_consecutive` wakeups in a row the next one must
degrade to a quiet notice. Real user input always resets the counter — the
user is back in the loop, so waking again is fine.
"""

from __future__ import annotations

MAX_CONSECUTIVE_WAKES = 3


class WakeBudget:
    """Per-session consecutive-wakeup counter; pure mechanism, no I/O."""

    def __init__(self, *, max_consecutive: int = MAX_CONSECUTIVE_WAKES) -> None:
        self._max = max(1, max_consecutive)
        self._counts: dict[str, int] = {}

    def allow(self, session: str) -> bool:
        """Whether one more wakeup may start a turn for this session."""
        return self._counts.get(session, 0) < self._max

    def record(self, session: str) -> None:
        """Count one wakeup delivered for this session."""
        self._counts[session] = self._counts.get(session, 0) + 1

    def reset(self, session: str) -> None:
        """Real user input arrived: the chain is broken."""
        self._counts.pop(session, None)


__all__ = ["MAX_CONSECUTIVE_WAKES", "WakeBudget"]
