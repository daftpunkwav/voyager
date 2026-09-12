"""Consumer cursors: per-subscriber consumption positions.

State is recovered from the cursor on restart, and any log range can be
replayed.
"""

from __future__ import annotations

import sqlite3
import threading

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cursors (
    name     TEXT PRIMARY KEY,
    last_seq INTEGER NOT NULL
);
"""


class CursorStore:
    """Cursor table for subscribers.

    May share the EventLog connection (for same-transaction consistency) or
    use a separate database. When sharing the connection, callers must pass
    the EventLog's lock (EventLog.lock): the event loop sets cursors on the
    event-loop thread while capability handlers append events on to_thread
    workers, and unsynchronized use of a single connection can interleave
    transactions.
    """

    def __init__(self, conn: sqlite3.Connection, lock: threading.Lock | None = None) -> None:
        self._conn = conn
        self._lock = lock if lock is not None else threading.Lock()
        self._conn.executescript(_SCHEMA)

    def get(self, name: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT last_seq FROM cursors WHERE name = ?", (name,)
            ).fetchone()
        return int(row[0]) if row else 0

    def set(self, name: str, last_seq: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO cursors (name, last_seq) VALUES (?, ?)"
                " ON CONFLICT(name) DO UPDATE SET last_seq = excluded.last_seq",
                (name, last_seq),
            )
            self._conn.commit()
