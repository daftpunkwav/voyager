"""Skill auto-organization: find repeated tool call sequences and surface
them as non-blocking skill proposals on the event stream.

Responsibilities:
- detect(): find repeated consecutive tool-call sequences in episodic memory
  (a "flow" involves at least two distinct tools — a repeated identical call
  is a loop for the LoopDetector to break, not a skill candidate)
- propose(): publish a skill.proposed event per hit via the injected emit
  callback. Non-blocking by design: no file is written here and the ask_user
  channel is never used; when the user agrees in conversation, the agent
  saves the skill through the propose_skill tool.
- maybe_propose(): cadence trigger - every N new tool episodes (hot-read
  setting, 0 = off) returns the proposal coroutine for the caller to schedule
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Awaitable, Callable

from agent.contracts import SettingsReader
from agent.memory.episodic import EpisodicMemory

log = logging.getLogger("agent.skills.organizer")

#: Emitted per proposal: {name, sequence, count}. The frontend turns it into
#: a sidebar notification; the vocabulary constant lives in platform_contracts.
SKILL_PROPOSED_EVENT = "skill.proposed"


class SkillOrganizer:
    def __init__(
        self,
        episodic: EpisodicMemory,
        *,
        emit: Callable[..., Awaitable[None]] | None = None,
        settings: SettingsReader | None = None,
    ) -> None:
        """emit mirrors RuntimeEvents.emit(type, **payload); None disables
        proposing (detection-only callers)."""
        self._episodic = episodic
        self._emit = emit
        self._settings = settings
        self._checked_at = 0  # tool-episode count at the last cadence check
        self._proposed: set[tuple[str, ...]] = set()  # sequences already surfaced

    def detect(self, *, min_count: int = 3, seq_len: int = 2) -> list[dict]:
        """Find repeated consecutive sequences in the episodic memory's tool
        call stream; sequences of one repeated identical tool are excluded
        (that is a loop, not a flow)."""
        entries = self._episodic.recent(limit=500, kind="tool")
        entries.reverse()  # chronological order
        by_run: dict[str, list[str]] = {}
        for e in entries:
            by_run.setdefault(e["run_id"] or "_", []).append(e["summary"])
        grams: Counter[tuple[str, ...]] = Counter()
        for names in by_run.values():
            for i in range(len(names) - seq_len + 1):
                grams[tuple(names[i : i + seq_len])] += 1
        return [
            {"sequence": list(seq), "count": n}
            for seq, n in grams.most_common()
            if n >= min_count and len(set(seq)) >= 2
        ]

    def maybe_propose(self) -> Awaitable[list[dict]] | None:
        """Cadence: once every `agent.skills.organize_every` new tool episodes
        (0 = off). Returns the proposal coroutine on trigger turns so the
        caller schedules it in the background, None otherwise."""
        if self._settings is None or self._emit is None:
            return None
        try:
            every = int(self._settings.get("agent.skills.organize_every") or 0)
        except (TypeError, ValueError):
            return None
        if every <= 0:
            return None
        total = self._episodic.count(kind="tool")
        if total - self._checked_at < every:
            return None
        self._checked_at = total
        return self.propose()

    async def propose(self, *, min_count: int = 3, seq_len: int = 2) -> list[dict]:
        """Publish skill.proposed events for repeated flows; each flow is
        surfaced only once per process lifetime (a restart may re-surface it,
        which is acceptable for a notification)."""
        out: list[dict] = []
        for hit in self.detect(min_count=min_count, seq_len=seq_len):
            seq = tuple(hit["sequence"])
            if seq in self._proposed:
                continue
            self._proposed.add(seq)
            proposal = {
                "name": "auto-" + "-".join(hit["sequence"])[:40],
                "sequence": hit["sequence"],
                "count": hit["count"],
            }
            try:
                await self._emit(SKILL_PROPOSED_EVENT, **proposal)
            except Exception:  # a failed notification must not break the turn
                log.warning("publishing skill proposal failed", exc_info=True)
                self._proposed.discard(seq)
                continue
            out.append(proposal)
        return out


__all__ = ["SKILL_PROPOSED_EVENT", "SkillOrganizer"]
