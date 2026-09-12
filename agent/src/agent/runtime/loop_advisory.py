"""Advisory loop guard: on the detector's FIRST trip, hand back a reminder
round instead of an abort; only a second trip ends the turn (hard break
becomes two-level).

Detection stays in runtime.loop_detection (pure detection, no consequences);
this module owns the consequence policy for the first trip and is one-shot
per ReAct invocation. The reminder rides a user-role nudge message — the same
channel as the idle-continue text — never a system rewrite.
"""

from __future__ import annotations

_ADVISORY_TEMPLATE = (
    "[advisory] 检测到你正在重复调用 {tool}(相同参数已在最近 {window} 次工具调用中出现 {threshold} 次)。"
    "换参数、换工具,或先用一句话向用户说明原因再继续;若确无必要继续,请直接给出结论。"
)


class LoopAdvisory:
    def __init__(self) -> None:
        self.used = False

    def on_trip(self, *, tool: str, threshold: int, window: int) -> str | None:
        """Reminder text for the first trip; None afterwards (the caller then
        aborts as before)."""
        if self.used:
            return None
        self.used = True
        return _ADVISORY_TEMPLATE.format(tool=tool, threshold=threshold, window=window)


__all__ = ["LoopAdvisory"]
