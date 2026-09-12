"""Approval memory (phase 21, T-21.3): remember L2 confirmations per
(tool + target), session-scoped or persistent, revocable.

- "session" grants live in memory only (a restart IS a new session);
- "always" grants persist in approvals.db and outlive restarts;
- the default is and stays "ask every time" — a grant only ever shortcuts a
  confirmation the user has already answered, it never widens the tool
  surface itself.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS approvals (
    tool      TEXT NOT NULL,
    target    TEXT NOT NULL,
    ts        REAL NOT NULL,
    PRIMARY KEY (tool, target)
);
"""


class ApprovalStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._session: set[tuple[str, str]] = set()

    def lookup(self, tool: str, target: str) -> str | None:
        """'always' | 'session' | None (ask). An empty target matches any
        target of the tool only when granted so (wildcard grants are stored
        as empty targets by the caller)."""
        with self._lock:
            if (tool, target) in self._session:
                return "session"
            row = self._conn.execute(
                "SELECT tool FROM approvals WHERE tool = ? AND target = ?", (tool, target)
            ).fetchone()
        return "always" if row else None

    def grant(self, tool: str, target: str, scope: str) -> None:
        if scope == "session":
            with self._lock:
                self._session.add((tool, target))
            return
        if scope == "always":
            with self._lock:
                self._conn.execute(
                    "INSERT OR REPLACE INTO approvals (tool, target, ts) VALUES (?, ?, ?)",
                    (tool, target, time.time()),
                )
                self._conn.commit()

    def list(self) -> list[dict]:
        """All grants: persistent rows plus the in-memory session grants."""
        with self._lock:
            rows = [
                {"tool": r[0], "target": r[1], "scope": "always", "ts": r[2]}
                for r in self._conn.execute(
                    "SELECT tool, target, ts FROM approvals ORDER BY ts DESC"
                ).fetchall()
            ]
            rows.extend(
                {"tool": t, "target": g, "scope": "session", "ts": 0.0}
                for t, g in sorted(self._session)
            )
        return rows

    def revoke(self, *, tool: str = "", target: str = "") -> int:
        """Remove matching grants (empty field = wildcard); returns the count."""
        removed = 0
        with self._lock:
            if not tool:
                removed += len(self._session)
                self._session.clear()
                cur = self._conn.execute("DELETE FROM approvals")
                removed += cur.rowcount
            else:
                before = len(self._session)
                self._session = {
                    (t, g) for t, g in self._session if t != tool or (target and g != target)
                }
                removed += before - len(self._session)
                if target:
                    cur = self._conn.execute(
                        "DELETE FROM approvals WHERE tool = ? AND target = ?", (tool, target)
                    )
                else:
                    cur = self._conn.execute("DELETE FROM approvals WHERE tool = ?", (tool,))
                removed += cur.rowcount
            self._conn.commit()
        return removed

    def close(self) -> None:
        self._conn.close()


__all__ = ["ApprovalStore"]
