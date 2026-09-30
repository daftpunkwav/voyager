"""Retention cutoff arithmetic shared by every bounded-growth store.

Every store that ages out rows/files (queue.db, journal.db, llm usage,
audit.db, upload staging) computes the same "strictly older than now -
days" boundary and accepts an injected `now` so tests can travel in time
without sleeping. Centralizing the expression keeps the boundary semantics
(strictly less, epoch seconds) identical everywhere instead of relying on
four copies staying in sync.
"""

from __future__ import annotations

import time

SECONDS_PER_DAY = 86400


def retention_cutoff(days: float, *, now: float | None = None) -> float:
    """Epoch-seconds boundary for "older than `days`": `now - days * 86400`.

    `now` defaults to the current clock; callers that already hold a
    timestamp (and tests) pass it explicitly. Stores delete rows with
    `ts < cutoff` (strictly less) so a row written exactly at the boundary
    survives one full window.
    """
    return (time.time() if now is None else now) - days * SECONDS_PER_DAY


__all__ = ["SECONDS_PER_DAY", "retention_cutoff"]
