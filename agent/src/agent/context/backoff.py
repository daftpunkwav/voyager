"""Compaction backoff: stop re-spending planner calls on a failing editor.

A failed LLM compaction (planner error, invalid plan, plan still over target)
tends to repeat: the transcript that confused the planner this round is mostly
still there next round, and the deterministic fallback does the real work
anyway. After repeated failures the guard suppresses the LLM path for a
window of compaction attempts - the window doubles with each further failure
and is capped - and any applied plan resets it, so a transient planner outage
costs a couple of wasted calls instead of one per round.
"""

from __future__ import annotations

#: Consecutive failed LLM compactions before the LLM path is suppressed
FAILS_BEFORE_BACKOFF = 2

#: Growth cap for the suppression window (counted in suppressed attempts)
SUPPRESSION_CAP = 8


class CompactionBackoff:
    """Failure-gated switch between the LLM editor and the mechanical path.

    The guard only sees LLM attempts: compactions served mechanically while
    suppressed record nothing - they prove nothing about the planner."""

    def __init__(
        self, *, threshold: int = FAILS_BEFORE_BACKOFF, cap: int = SUPPRESSION_CAP
    ) -> None:
        self._threshold = max(1, threshold)
        self._cap = max(1, cap)
        self._fails = 0
        self._blocked = 0
        self._window = 0

    def allow_llm(self) -> bool:
        """Whether the next compaction may call the planner; a suppressed
        attempt consumes one slot of the suppression window."""
        if self._blocked > 0:
            self._blocked -= 1
            return False
        return True

    def record(self, *, plan_applied: bool) -> None:
        """Record one LLM compaction outcome: an applied plan resets the
        guard; a failure past the threshold opens the next suppression
        window, doubling it while failures keep coming."""
        if plan_applied:
            self._fails = 0
            self._blocked = 0
            self._window = 0
            return
        self._fails += 1
        if self._fails >= self._threshold:
            self._window = min(max(self._window * 2, 1), self._cap)
            self._blocked = self._window


__all__ = ["FAILS_BEFORE_BACKOFF", "SUPPRESSION_CAP", "CompactionBackoff"]
