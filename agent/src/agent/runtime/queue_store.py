"""Durable job queue persistence: queue.db rows, cron evaluation and restart
recovery (the storage half; dispatch policy lives in scheduler.py).

Jobs are data (kind + payload + schedule); the executor maps kinds to
handlers at runtime, so a persisted row survives restarts even though its
handler is re-registered fresh each boot. Delivery is at-least-once: a job
that was running during a crash goes back to pending and re-fires. Cron jobs
skip missed slots: after each run the next slot is computed from the current
time, so a long outage never replays the backlog slot by slot.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from platform_contracts import ErrorSuffix, ServiceError, retention_cutoff

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}',
    cron        TEXT NOT NULL DEFAULT '',
    run_at      REAL NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending',
    created_ts  REAL NOT NULL,
    last_run_ts REAL NOT NULL DEFAULT 0,
    last_error  TEXT NOT NULL DEFAULT '',
    attempts    INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_jobs_due ON jobs(status, priority DESC, run_at);
"""

_MAX_PAYLOAD = 4000
_MINUTE = 60.0


@dataclass(frozen=True)
class Job:
    id: str
    kind: str
    payload: dict
    cron: str
    run_at: float
    priority: int


def _row(r: tuple) -> Job | None:
    """Decode one row; None when the stored payload is not valid JSON (a row
    truncated by an older version — callers quarantine it instead of
    crashing every subsequent tick)."""
    try:
        payload = json.loads(r[2])
    except json.JSONDecodeError:
        return None
    return Job(
        id=r[0],
        kind=r[1],
        payload=payload,
        cron=r[3],
        run_at=r[4],
        priority=r[5],
    )


def _cron_dow_to_python(field: str) -> str:
    """Rewrite one day-of-week field from cron's 0=Sunday convention to
    Python weekday() values (0=Monday): each number n becomes (n - 1) % 7."""

    def _shift(token: str) -> str:
        token = token.strip()
        try:
            return str((int(token) - 1) % 7)
        except ValueError:
            return token

    out = []
    for part in field.split(","):
        if "-" in part and not part.strip().startswith("-"):
            lo, _, hi = part.partition("-")
            out.append(f"{_shift(lo)}-{_shift(hi)}")
        else:
            out.append(_shift(part))
    return ",".join(out)


def _field_matches(field: str, value: int) -> bool:
    """One cron field against one value: `*`, `*/n`, `a-b`, lists `a,b,c`,
    plain numbers. A range with lo > hi wraps (standard cron: `22-2` hours =
    22,23,0,1,2) — required here because the DOW rewrite maps cron's 0=Sunday
    onto Python's 0=Monday with a cyclic shift, so a range that contains
    Sunday (`0-3`, `0-6`) becomes a reversed pair (`6-2`, `6-5`) that only a
    wrap matches."""
    field = field.strip()
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if part.startswith("*/"):
            try:
                step = int(part[2:])
            except ValueError:
                return False
            if step > 0 and value % step == 0:
                return True
        elif "-" in part and not part.startswith("-"):
            lo, _, hi = part.partition("-")
            try:
                lo_i, hi_i = int(lo), int(hi)
            except ValueError:
                return False
            if lo_i <= hi_i:
                if lo_i <= value <= hi_i:
                    return True
            elif value >= lo_i or value <= hi_i:  # wrap: 6-2 = 6,0,1,2
                return True
        else:
            try:
                if int(part) == value:
                    return True
            except ValueError:
                return False
    return False


def next_cron_time(expr: str, after_ts: float) -> float | None:
    """Next fire time (epoch seconds, machine-local calendar) strictly after
    after_ts for a 5-field cron expression; None when malformed or no
    occurrence within ~370 days.

    The scan skips whole spans whose coarser field already rules them out
    (a month mismatch jumps to the next month, a day/hour mismatch to the
    next day/hour) instead of stepping minute by minute — the visited
    minutes are the same candidate set, so the first match (or the None
    after 370 days) is identical, just reached with orders of magnitude
    fewer iterations. Note on DST: all arithmetic is wall-clock on
    zone-aware datetimes, so in a zone where a jump target (e.g. midnight)
    falls inside a spring-forward gap the timestamp is taken with the
    pre-transition offset; minute-stepping would land on the shifted wall
    time. Identical in DST-free zones (this deployment runs in UTC+8).
    """
    fields = expr.split()
    if len(fields) != 5:
        return None
    minute_f, hour_f, dom_f, mon_f = fields[0], fields[1], fields[2], fields[3]
    dow_f = _cron_dow_to_python(fields[4])  # pure field rewrite: hoisted out of the scan
    start = datetime.fromtimestamp(after_ts).astimezone() + timedelta(minutes=1)
    start = start.replace(second=0, microsecond=0)
    minute_end = start + timedelta(days=370)
    cur = start
    while cur < minute_end:
        if not _field_matches(mon_f, cur.month):
            # Land on the 1st of the next month at 00:00 (+32 days cannot
            # stay inside a 31-day-max month).
            cur = (cur.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
            continue
        if not (_field_matches(dom_f, cur.day) and _field_matches(dow_f, cur.weekday())):
            cur = cur.replace(hour=0, minute=0) + timedelta(days=1)
            continue
        if not _field_matches(hour_f, cur.hour):
            cur = cur.replace(minute=0) + timedelta(hours=1)
            continue
        if not _field_matches(minute_f, cur.minute):
            cur += timedelta(minutes=1)
            continue
        return cur.timestamp()
    return None


class QueueStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._lock = threading.Lock()

    def _migrate(self) -> None:
        """Idempotent in-place upgrade of databases created before the retry
        count moved out of last_error: ALTER TABLE adds the missing column
        (older rows default to attempts=0 = "not yet retried", matching the
        previous empty-error semantics). Same pattern as the other stores
        (llm.store, notes.store, graph.index_queue)."""
        try:
            self._conn.execute("ALTER TABLE jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    def enqueue(
        self,
        *,
        kind: str,
        payload: dict | None = None,
        delay_s: float = 0,
        cron: str = "",
        priority: int = 0,
        run_at: float | None = None,
        job_id: str = "",
    ) -> str:
        """Insert one pending job; explicit run_at wins over delay_s. Returns
        the job id (caller-supplied ids are upserted, so re-enqueueing the
        same logical job is idempotent)."""
        jid = job_id or f"{kind}-{uuid.uuid4().hex[:12]}"
        when = run_at if run_at is not None else time.time() + max(0.0, delay_s)
        blob = json.dumps(payload or {}, ensure_ascii=False, default=str)
        if len(blob) > _MAX_PAYLOAD:
            # A truncated blob would not parse back; refuse instead of
            # poisoning the queue for every later tick.
            raise ServiceError(
                "queue",
                ErrorSuffix.INVALID_INPUT,
                f"job payload is {len(blob)} chars, over the {_MAX_PAYLOAD}-char storage limit",
                hint="shrink the payload (shorter text, fewer fields) and retry",
            )
        with self._lock:
            self._conn.execute(
                "INSERT INTO jobs (id, kind, payload, cron, run_at, priority, status, created_ts)"
                " VALUES (?,?,?,?,?,?, 'pending', ?)"
                " ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, payload=excluded.payload,"
                " cron=excluded.cron, run_at=excluded.run_at, priority=excluded.priority,"
                " status='pending', last_error='', attempts=0",
                (jid, kind, blob, cron, when, priority, time.time()),
            )
            self._conn.commit()
        return jid

    def due(self, *, now: float | None = None, limit: int = 10) -> list[Job]:
        """Pending jobs whose time has come, highest priority first, oldest
        first within a priority. Rows with an unparseable payload are
        quarantined as 'failed' so one bad row cannot stall the queue."""
        current = time.time() if now is None else now
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, kind, payload, cron, run_at, priority FROM jobs"
                " WHERE status = 'pending' AND run_at <= ?"
                " ORDER BY priority DESC, run_at ASC LIMIT ?",
                (current, max(1, limit)),
            ).fetchall()
            jobs = self._decode(rows, quarantine=True)
        return jobs

    def _decode(self, rows: list[tuple], *, quarantine: bool) -> list[Job]:
        """Decode rows. With quarantine=True (the dispatch path), rows with an
        unparseable payload are marked 'failed' so one bad row cannot stall
        the queue; read paths keep the row visible with an empty payload
        instead of crashing or hiding it."""
        jobs: list[Job] = []
        quarantined = False
        for r in rows:
            job = _row(r)
            if job is None:
                if quarantine:
                    self._conn.execute(
                        "UPDATE jobs SET status = 'failed', last_error = 'corrupt payload' WHERE id = ?",
                        (r[0],),
                    )
                    quarantined = True
                    continue
                job = Job(id=r[0], kind=r[1], payload={}, cron=r[3], run_at=r[4], priority=r[5])
            jobs.append(job)
        if quarantined:
            self._conn.commit()
        return jobs

    def mark_started(self, job_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE jobs SET status = 'running', last_run_ts = ? WHERE id = ?",
                (time.time(), job_id),
            )
            self._conn.commit()

    def mark_done(self, job_id: str) -> None:
        """One-shot jobs complete; cron jobs reschedule to the first slot
        after *now* — slots missed while the process was down are skipped,
        never replayed one by one."""
        with self._lock:
            row = self._conn.execute(
                "SELECT cron, run_at FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return
            cron = row[0]
            if cron:
                nxt = next_cron_time(cron, time.time())
                if nxt is not None:
                    self._conn.execute(
                        "UPDATE jobs SET status = 'pending', run_at = ? WHERE id = ?",
                        (nxt, job_id),
                    )
                    self._conn.commit()
                    return
            self._conn.execute("UPDATE jobs SET status = 'done' WHERE id = ?", (job_id,))
            self._conn.commit()

    def mark_failed(self, job_id: str, error: str) -> None:
        """A failed one-shot goes back to pending once (retry ~30s later); a
        failed cron job reschedules like a done one. After a retry the
        caller may give up by deleting; this store keeps retries bounded via
        the attempts column (one mark_failed delivery = one attempt: the
        first failure retries, the second gives up — a single retry keeps
        the schema minimal)."""
        with self._lock:
            row = self._conn.execute(
                "SELECT cron, run_at, attempts FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return
            cron, run_at, attempts = row[0], row[1], row[2]
            retried = attempts == 0
            attempts += 1
            if cron:
                nxt = next_cron_time(cron, time.time())
                self._conn.execute(
                    "UPDATE jobs SET status = ?, run_at = ?, last_error = ?, attempts = ?"
                    " WHERE id = ?",
                    (
                        "pending" if nxt is not None else "failed",
                        nxt or run_at,
                        error[:500],
                        attempts,
                        job_id,
                    ),
                )
            elif retried:
                self._conn.execute(
                    "UPDATE jobs SET status = 'pending', run_at = ?, last_error = ?,"
                    " attempts = ? WHERE id = ?",
                    (time.time() + 30.0, error[:500], attempts, job_id),
                )
            else:
                self._conn.execute(
                    "UPDATE jobs SET status = 'failed', last_error = ?, attempts = ? WHERE id = ?",
                    (error[:500], attempts, job_id),
                )
            self._conn.commit()

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE jobs SET status = 'cancelled' WHERE id = ? AND status IN ('pending','running')",
                (job_id,),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def list(
        self, *, statuses: tuple[str, ...] = ("pending", "running"), limit: int = 50
    ) -> list[Job]:
        marks = ",".join("?" for _ in statuses)
        with self._lock:
            # Bound parameters only; the IN-list length drives the mark count.
            rows = self._conn.execute(
                f"SELECT id, kind, payload, cron, run_at, priority FROM jobs"  # nosec B608  # nosemgrep
                f" WHERE status IN ({marks}) ORDER BY run_at ASC LIMIT ?",
                (*statuses, max(1, limit)),
            ).fetchall()
            return self._decode(rows, quarantine=False)

    def recover(self) -> int:
        """Startup recovery: jobs stuck 'running' from a crash go back to
        pending (idempotent: done/cron-slot rows are untouched)."""
        with self._lock:
            cur = self._conn.execute("UPDATE jobs SET status = 'pending' WHERE status = 'running'")
            self._conn.commit()
        return cur.rowcount

    def purge_finished_older_than_days(self, days: int, *, now: float | None = None) -> int:
        """Startup purge of finished one-shot rows (done/failed/cancelled,
        no cron schedule) past the retention window.

        Terminal rows have no consumer after their single retry window
        elapses (the jobs view reads the event log, not this table), so they
        are write-only residue that would otherwise accumulate one row per
        delayed job forever. Cron definitions keep cycling pending/running
        and are never touched, even a cancelled one (the definition stays
        visible); pending/running rows are never touched. Returns the row
        count."""
        cutoff = retention_cutoff(days, now=now)
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM jobs WHERE cron = '' AND run_at < ?"
                " AND status IN ('done', 'failed', 'cancelled')",
                (cutoff,),
            )
            self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()


__all__ = ["Job", "QueueStore", "next_cron_time"]
