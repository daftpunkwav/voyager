"""Advisory loop guard: on the detector's FIRST trip, hand back a reminder
round instead of an abort; only a second trip ends the turn (hard break
becomes two-level).

Detection stays in runtime.loop_detection (pure detection, no consequences);
this module owns the consequence policy for the first trip and is one-shot
per ReAct invocation. The reminder rides a user-role nudge message — the same
channel as the idle-continue text — never a system rewrite.
"""

from __future__ import annotations

from agent.prompts import P, render


class LoopAdvisory:
    def __init__(self) -> None:
        self.used = False

    def on_trip(self, *, tool: str, threshold: int, window: int) -> str | None:
        """Reminder text for the first trip; None afterwards (the caller then
        aborts as before)."""
        if self.used:
            return None
        self.used = True
        return render(P.runtime.loop_advisory, tool=tool, threshold=threshold, window=window)


__all__ = ["LoopAdvisory"]
