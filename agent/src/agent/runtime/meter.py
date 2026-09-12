"""Meter: bounded ring window of MeterRecord for llm/tool calls, plus
synchronous persistence (cross-restart daily quota and tool-call counts).

tokens_used_today() reads the store only (UTC day boundary); totals() is an
overview over the window and never affects quota correctness. Tool rows are
persisted as call counts (no tokens) so usage views survive restarts; the
quota itself stays llm-token based.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from agent.runtime.meter_store import MeterStore


@dataclass(frozen=True)
class MeterRecord:
    kind: str  # "llm" | "tool"
    name: str  # model name or tool name
    ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    ok: bool = True
    ts: float = field(default_factory=time.time)


class Meter:
    """In-memory metering plus an optional persistent store (cross-restart daily quota);
    ledger export remains the sink's job.

    records is a bounded ring window (cap 4096): long-running processes no longer accumulate
    without limit. The authoritative data for the daily token quota lives in the store
    (tokens_used_today reads the store); the window only serves totals() overviews and
    debugging -- evicting the oldest entries never affects quota correctness.
    """

    #: In-memory record window cap; llm/tool calls are both recorded -- 4096 entries suffice
    #: for debugging and keep memory bounded
    _RECORDS_CAP = 4096

    def __init__(self, sink: Any = None, store: MeterStore | None = None) -> None:
        self.records: deque[MeterRecord] = deque(maxlen=self._RECORDS_CAP)
        self._sink = sink
        self._store = store

    def record(self, rec: MeterRecord) -> None:
        self.records.append(rec)
        # Both kinds persist synchronously (llm: cross-restart daily quota; tool:
        # call counts for usage views); failed calls (ok=False) are recorded as
        # before (record runs in finally), and rec.ts pins the UTC day boundary
        if self._store is not None:
            self._store.add(
                rec.kind,
                rec.input_tokens,
                rec.output_tokens,
                calls=1,
                ts=rec.ts,
            )
        if self._sink is not None:
            self._sink(rec)

    def totals(self) -> dict[str, int]:
        return {
            "llm_calls": sum(1 for r in self.records if r.kind == "llm"),
            "tool_calls": sum(1 for r in self.records if r.kind == "tool"),
            "input_tokens": sum(r.input_tokens for r in self.records),
            "output_tokens": sum(r.output_tokens for r in self.records),
        }

    def tokens_used_today(self, *, now: float | None = None) -> int:
        """Tokens used today (input+output total); the calendar day boundary is UTC (pinned
        by unit tests).

        With a persistent store, only the store is read: record persists synchronously, so the
        store is authoritative and in-memory records are not double-counted. Without a store,
        pure in-memory aggregation applies (comparing UTC days of rec.ts; now injects the
        current time for tests, defaulting to the real clock).
        """
        if self._store is not None:
            return self._store.tokens_used_today(now=now)
        current = time.time() if now is None else now
        today = time.gmtime(current)[:3]
        return sum(
            r.input_tokens + r.output_tokens for r in self.records if time.gmtime(r.ts)[:3] == today
        )

    def tool_calls_today(self, *, now: float | None = None) -> int:
        """Tool-call count today: the persisted kind='tool' row when a store is
        wired, else the in-memory window (a best-effort view, not a quota)."""
        if self._store is not None:
            return self._store.calls_today(kind="tool", now=now)
        current = time.time() if now is None else now
        today = time.gmtime(current)[:3]
        return sum(1 for r in self.records if r.kind == "tool" and time.gmtime(r.ts)[:3] == today)

    def close(self) -> None:
        """Close the persistent store (for tests and process exit); an in-memory Meter is a
        no-op."""
        if self._store is not None:
            self._store.close()


__all__ = ["Meter", "MeterRecord"]
