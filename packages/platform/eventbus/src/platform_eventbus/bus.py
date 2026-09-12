"""Publish/subscribe: in-process asyncio queue fan-out plus
log-backed cursor replay.

The in-memory queues are only an acceleration channel; the log is the source
of truth. A subscriber that falls behind (queue full) is just flagged as
lagged, and read_missed / replay backfill it from the log, so no event is
lost.
"""

from __future__ import annotations

import asyncio
import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass, field

from platform_contracts import Event

from platform_eventbus.cursor import CursorStore
from platform_eventbus.log import EventLog


@dataclass
class Subscription:
    """In-process subscription.

    lagged=True means events were not pushed because the queue was full and
    must be backfilled via read_missed. last_seq tracks the highest consumed
    seq so consumers can advance their cursor (no re-consumption after a
    crash).

    Patterns can be added or dropped at runtime: add_patterns / drop_patterns
    take effect immediately in matches(). Already-published events are not
    re-matched; future events match the new patterns without resubscribing.
    Each event is matched against the patterns present at enqueue time; both
    list mutation and iteration happen synchronously on the event loop
    (no await in between), so there is no race under the single-threaded
    event-loop convention.
    """

    _pattern_list: list[str] = field(default_factory=list)
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    lagged: bool = False
    last_seq: int = 0

    @property
    def patterns(self) -> tuple[str, ...]:
        """Snapshot of the current subscription patterns (add/drop take effect
        immediately; order is insertion order)."""
        return tuple(self._pattern_list)

    def matches(self, event_type: str) -> bool:
        return any(fnmatch.fnmatchcase(event_type, p) for p in self._pattern_list)

    def add_patterns(self, *patterns: str) -> None:
        """Append subscription patterns at runtime (deduplicated, order kept);
        patterns already present are a no-op."""
        for p in patterns:
            if p not in self._pattern_list:
                self._pattern_list.append(p)

    def drop_patterns(self, *patterns: str) -> None:
        """Remove subscription patterns at runtime; absent patterns are a no-op."""
        for p in patterns:
            if p in self._pattern_list:
                self._pattern_list.remove(p)

    async def get(self, timeout: float | None = None) -> Event:
        """Receive the next pushed event."""
        if timeout is None:
            seq, event = await self.queue.get()
        else:
            seq, event = await asyncio.wait_for(self.queue.get(), timeout)
        self.last_seq = seq
        return event


class EventBus:
    """In-process push delivery on top of a persistent log.

    Cross-process consumers poll the log with read_missed, advancing a cursor.
    """

    def __init__(self, log: EventLog, *, queue_size: int = 1000) -> None:
        self._log = log
        self._queue_size = queue_size
        self._subs: list[Subscription] = []

    @property
    def log(self) -> EventLog:
        return self._log

    async def publish(self, event: Event) -> int:
        """Append to the log first (source of truth), then push to in-process
        subscribers. Returns the seq."""
        seq = await asyncio.to_thread(self._log.append, event)
        for sub in self._subs:
            if not sub.matches(event.type):
                continue
            try:
                sub.queue.put_nowait((seq, event))
            except asyncio.QueueFull:
                sub.lagged = True
        return seq

    def subscribe(self, *patterns: str) -> Subscription:
        sub = Subscription(_pattern_list=list(patterns), queue=asyncio.Queue(self._queue_size))
        self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        if sub in self._subs:
            self._subs.remove(sub)

    def replay(
        self, after_seq: int = 0, types: Iterable[str] | None = None, limit: int = 500
    ) -> list[tuple[int, Event]]:
        """Replay an arbitrary range from the log."""
        return self._log.read_after(after_seq=after_seq, types=types, limit=limit)

    def read_missed(
        self,
        subscriber: str,
        cursors: CursorStore,
        types: Iterable[str] | None = None,
        limit: int = 500,
    ) -> list[tuple[int, Event]]:
        """Cursor-based catch-up: read events after the subscriber's cursor
        and advance the cursor."""
        rows = self._log.read_after(after_seq=cursors.get(subscriber), types=types, limit=limit)
        if rows:
            cursors.set(subscriber, rows[-1][0])
        return rows
