"""Persistence for Meter usage (the resource dimension): daily totals land
in sqlite.

Token totals and call counts are accumulated per (UTC calendar day, kind);
the database file meter.db sits next to events.db. Daily quota /
get_resource_quota read the same persisted source via Meter, so daily totals
survive process restarts. Only totals are stored, not a per-call ledger
(quota depends on the daily sum alone); calls rejected by quota are not
recorded (consistent with the in-memory accounting). Tool rows carry counts
only (no tokens).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meter_tokens (
    day_utc       TEXT NOT NULL,   -- 'YYYY-MM-DD' UTC calendar day
    kind          TEXT NOT NULL,   -- 'llm' (tokens + calls) | 'tool' (calls only)
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    calls         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day_utc, kind)
);
CREATE TABLE IF NOT EXISTS meter_models (
    day_utc       TEXT NOT NULL,   -- 'YYYY-MM-DD' UTC calendar day
    model         TEXT NOT NULL,   -- model name as metered
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day_utc, model)
);
"""


def _utc_day(ts: float) -> str:
    """Epoch seconds -> 'YYYY-MM-DD' (UTC day boundary, as in Meter.tokens_used_today)."""
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


class MeterStore:
    """Persistence handle for daily token totals; thread lock + check_same_thread=False
    (same as episodic)."""

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._migrate()

    def _migrate(self) -> None:
        """Databases created before the calls column exist without it; add it
        in place (idempotent)."""
        with self._lock:
            cols = {row[1] for row in self._conn.execute("PRAGMA table_info(meter_tokens)")}
            if "calls" not in cols:
                self._conn.execute(
                    "ALTER TABLE meter_tokens ADD COLUMN calls INTEGER NOT NULL DEFAULT 0"
                )
                self._conn.commit()

    def add(
        self,
        kind: str,
        input_tokens: int,
        output_tokens: int,
        *,
        calls: int = 0,
        ts: float | None = None,
    ) -> None:
        """Accumulate into the UTC day of ts; when ts is omitted, the real clock is used
        (same default source as MeterRecord)."""
        day = _utc_day(time.time() if ts is None else ts)
        with self._lock:
            self._conn.execute(
                "INSERT INTO meter_tokens (day_utc, kind, input_tokens, output_tokens, calls)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(day_utc, kind) DO UPDATE SET"
                " input_tokens = input_tokens + excluded.input_tokens,"
                " output_tokens = output_tokens + excluded.output_tokens,"
                " calls = calls + excluded.calls",
                (day, kind, int(input_tokens), int(output_tokens), int(calls)),
            )
            self._conn.commit()

    def add_model(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        *,
        cached_tokens: int = 0,
        ts: float | None = None,
    ) -> None:
        """Accumulate per-model usage into the UTC day of ts (cost view)."""
        day = _utc_day(time.time() if ts is None else ts)
        with self._lock:
            self._conn.execute(
                "INSERT INTO meter_models (day_utc, model, input_tokens, output_tokens, cached_tokens)"
                " VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(day_utc, model) DO UPDATE SET"
                " input_tokens = input_tokens + excluded.input_tokens,"
                " output_tokens = output_tokens + excluded.output_tokens,"
                " cached_tokens = cached_tokens + excluded.cached_tokens",
                (day, model, int(input_tokens), int(output_tokens), int(cached_tokens)),
            )
            self._conn.commit()

    def calls_today(self, *, now: float | None = None, kind: str = "tool") -> int:
        """Today's call count for one kind (tool by default)."""
        day = _utc_day(time.time() if now is None else now)
        with self._lock:
            row = self._conn.execute(
                "SELECT calls FROM meter_tokens WHERE day_utc = ? AND kind = ?", (day, kind)
            ).fetchone()
        return int(row[0]) if row else 0

    def tokens_used_today(self, *, now: float | None = None, kind: str = "llm") -> int:
        """Today's input+output total (the llm row only by default), matching the in-memory
        aggregation semantics."""
        day = _utc_day(time.time() if now is None else now)
        with self._lock:
            row = self._conn.execute(
                "SELECT input_tokens, output_tokens FROM meter_tokens"
                " WHERE day_utc = ? AND kind = ?",
                (day, kind),
            ).fetchone()
        return (row[0] + row[1]) if row else 0

    def models_today(self, *, now: float | None = None) -> list[tuple[str, int, int, int]]:
        """Today's per-model (name, input, output, cached) rows behind the
        cost view; empty when nothing was metered today."""
        day = _utc_day(time.time() if now is None else now)
        with self._lock:
            rows = self._conn.execute(
                "SELECT model, input_tokens, output_tokens, cached_tokens FROM meter_models"
                " WHERE day_utc = ?",
                (day,),
            ).fetchall()
        return [(str(r[0]), int(r[1]), int(r[2]), int(r[3])) for r in rows]

    def purge_older_than_days(self, days: int, *, now: float | None = None) -> int:
        """Delete day rows older than today_utc - days (strictly less), returning the
        number of rows removed.

        Startup-time maintenance: keeps meter_tokens/meter_models from
        accumulating unboundedly across dates. Day boundaries match
        tokens_used_today (time.gmtime, UTC calendar days).
        """
        base = time.time() if now is None else now
        cutoff = time.strftime("%Y-%m-%d", time.gmtime(base - days * 86400))
        with self._lock:
            cur = self._conn.execute("DELETE FROM meter_tokens WHERE day_utc < ?", (cutoff,))
            self._conn.execute("DELETE FROM meter_models WHERE day_utc < ?", (cutoff,))
            self._conn.commit()
            return cur.rowcount

    def close(self) -> None:
        self._conn.close()
