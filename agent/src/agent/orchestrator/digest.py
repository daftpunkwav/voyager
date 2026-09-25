"""Digest: maintains subagent status cards.

The master only holds "what each subagent is doing" cards plus basic info by
default; each subagent owns its full task context - context is never shared
directly and must be requested via tools when needed.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class Digest:
    subagent_id: str
    name: str
    goal: str
    status: str
    last_step: str = ""
    ts: float = field(default_factory=time.time)


class DigestStore:
    #: Card cap: runs are unbounded while cards only surface in list/render,
    #: so over the cap the **oldest terminal** cards are evicted (active and
    #: freshly updated cards are never evicted); same trade-off as
    #: Spawner.TERMINAL_INSTANCE_CAP
    _MAX_CARDS = 200
    _TERMINAL = frozenset({"completed", "failed", "cancelled"})

    def __init__(self) -> None:
        self._cards: dict[str, Digest] = {}
        # request_context renders on a worker thread via invoke's to_thread,
        # concurrent with upsert on the event-loop thread: adding keys during
        # dict iteration raises RuntimeError, so read-modify-write shares a lock
        self._lock = threading.Lock()

    STEP_MAX = 120  # matches the agent.step SSE truncation

    def upsert(self, instance) -> Digest:
        """Sync a card from a SubagentInstance (duck-typed, avoiding a circular
        dependency; data comes through the instance's public interface, not
        the state machine's internals)."""
        card = Digest(
            subagent_id=instance.id,
            name=instance.name,
            goal=instance.task.goal,
            status=instance.status.value,
            last_step=instance.last_step_summary()[: self.STEP_MAX],
            ts=time.time(),
        )
        with self._lock:
            self._cards[instance.id] = card
            self._trim(active_id=instance.id)
        return card

    def _trim(self, *, active_id: str) -> None:
        """Caller must hold _lock (same lock domain as upsert, avoiding
        interleaved read-modify-write)."""
        if len(self._cards) <= self._MAX_CARDS:
            return
        stale = sorted(
            (
                c
                for c in self._cards.values()
                if c.subagent_id != active_id and c.status.lower() in self._TERMINAL
            ),
            key=lambda c: c.ts,
        )
        for c in stale[: len(self._cards) - self._MAX_CARDS]:
            self._cards.pop(c.subagent_id, None)

    def remove(self, subagent_id: str) -> None:
        with self._lock:
            self._cards.pop(subagent_id, None)

    def list(self) -> list[Digest]:
        with self._lock:
            return sorted(self._cards.values(), key=lambda c: c.ts, reverse=True)

    def render(self) -> str:
        cards = self.list()
        if not cards:
            return ""
        lines = []
        for c in cards:
            tail = f" | recent: {c.last_step}" if c.last_step else ""
            lines.append(f"- [{c.status}] {c.name}({c.subagent_id}): {c.goal}{tail}")
        return "\n".join(lines)
