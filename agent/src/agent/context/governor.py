"""Per-instance context authority: computes the usage status,
decides when the transcript needs restructuring, and drives the LLM editor
with a deterministic fallback.

The governor is the harness half of LLM-driven context management: it owns
the trigger policy (threshold on usable-window usage), while the decision of
what to keep/summarize/drop belongs to the planner call inside
editor.compact_transcript. One governor is built per turn from the
spawn-time budget snapshot, so setting changes apply to the next turn
without touching the running one.
"""

from __future__ import annotations

from typing import Any

from agent.context.backoff import CompactionBackoff
from agent.context.editor import compact_transcript
from agent.context.usage import (
    ContextWindow,
    UsageTracker,
    over_threshold,
    usage_status,
)
from agent.llm import LLMClient


class ContextGovernor:
    """Threshold-gated entry into the LLM context editor.

    The trigger threshold is expressed as a percent of the usable window and
    should sit above the post-compact target (defaults: 75% vs 40%); when the
    transcript is between the two, enforce() fires but the editor no-ops
    (nothing to gain), and the check simply repeats next round.
    """

    def __init__(
        self,
        *,
        window: ContextWindow,
        auto_compact_at: int,
        compact_target: int,
        fallback_budget: int,
        tracker: UsageTracker,
        llm: LLMClient,
        planner: LLMClient | None = None,
        guard: CompactionBackoff | None = None,
    ) -> None:
        self._window = window
        self._auto_compact_at = auto_compact_at
        self._compact_target = compact_target
        self._fallback_budget = fallback_budget
        self._tracker = tracker
        self._llm = llm
        self._planner = planner
        self._guard = guard

    @property
    def window(self) -> ContextWindow:
        return self._window

    def target_tokens(self) -> int:
        """Post-compact target: the explicit setting when positive, otherwise
        40% of the usable window."""
        if self._compact_target > 0:
            return self._compact_target
        return int(self._window.usable * 0.4)

    def status(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Usage facts for the given transcript (estimate + reported anchor)."""
        return usage_status(
            self._window,
            messages,
            self._tracker,
            auto_compact_at=self._auto_compact_at,
        )

    def over_threshold(self, messages: list[dict[str, Any]]) -> bool:
        return over_threshold(self.status(messages))

    async def enforce(self, messages: list[dict[str, Any]]) -> dict[str, Any] | None:
        """Per-round hook: compact only when the threshold is crossed;
        returns the editor report or None when nothing fired."""
        if not self.over_threshold(messages):
            return None
        return await self.compact(messages)

    async def compact(
        self, messages: list[dict[str, Any]], *, target: int | None = None
    ) -> dict[str, Any] | None:
        """Unconditional compaction attempt (proactive tool calls, overflow
        recovery); None when already within target.

        The editor's planning call runs on the injected planner client when
        the context_planner purpose is routed (a lighter model suffices: the
        planner only classifies and summarizes segments); without one it
        shares the chat client as before. The backoff guard suppresses the
        LLM path after repeated failures - see agent.context.backoff."""
        planner = self._planner if self._planner is not None else self._llm
        allow = self._guard.allow_llm() if self._guard is not None else True
        report = await compact_transcript(
            messages,
            planner,
            target=target if target is not None else self.target_tokens(),
            fallback_budget=self._fallback_budget,
            allow_llm=allow,
        )
        if report is not None:
            # The transcript was restructured in place: the provider anchor
            # measured the pre-compact prefix and is now stale; drop it so
            # the status reflects the shorter transcript instead of pinning
            # above the trigger until the next LLM round reports.
            self._tracker.reset()
        if self._guard is not None and allow and report is not None:
            # Only LLM attempts feed the guard; suppressed compactions ran
            # mechanically and prove nothing about the planner
            self._guard.record(plan_applied=report["mode"] == "plan")
        return report


__all__ = ["ContextGovernor"]
