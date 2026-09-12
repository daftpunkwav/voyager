"""Multi-session persistence: every chat session survives restarts.

Responsibilities:
- SessionMeta / SessionSnapshot: the persisted shape of one chat session
  (metadata for listings; the full snapshot including bounded history for
  instance rebuild)
- SessionStore: keyed SQLite rows (sessions + a meta table for the active
  session pointer); atomic upserts, tolerant loads - a corrupt row is skipped
  instead of breaking startup or listings
- Legacy migration: the pre-multi-session store kept ONE row in a `session`
  table (key="chat"); on open, that row is copied into a real session so the
  old conversation keeps working. The legacy table is left in place.

Task instances have checkpoint resume; this store deliberately covers only
conversational instances, which resume_from_checkpoint excludes.
"""

from __future__ import annotations

import builtins
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: Session ids end up in event payloads and DB keys only; the strict pattern
#: keeps anything path-like or control-ish out by construction
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

#: Legacy single-row table (pre-multi-session); read-only after migration
_LEGACY_TABLE = "session"
_DEFAULT_SESSION_ID = "chat"


def is_valid_session_id(session_id: str) -> bool:
    """Public shape check (also used by the gateway and Master as an early
    guard so a malformed id becomes a readable rejection, never a lost
    message or a stored junk row)."""
    return bool(_SESSION_ID_RE.match(session_id or ""))


def _valid_session_id(session_id: str) -> bool:
    return is_valid_session_id(session_id)


@dataclass(frozen=True)
class SessionMeta:
    """Listing view of one session (no history payload)."""

    session_id: str
    title: str
    persona: str
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class SessionSnapshot:
    """Persisted state of one chat session."""

    session_id: str
    title: str = ""
    persona: str = "orchestrator"
    goal: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)
    created_at: float = 0.0
    updated_at: float = 0.0
    saved_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "persona": self.persona,
            "goal": self.goal,
            "history": self.history,
            "active_tools": self.active_tools,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "saved_at": self.saved_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SessionSnapshot:
        history = raw.get("history")
        if not isinstance(history, list):
            history = []
        return cls(
            session_id=str(raw.get("session_id") or ""),
            title=str(raw.get("title") or ""),
            persona=str(raw.get("persona") or "orchestrator"),
            goal=str(raw.get("goal") or ""),
            history=[dict(m) for m in history if isinstance(m, dict)],
            active_tools=[str(t) for t in raw.get("active_tools") or ()],
            created_at=float(raw.get("created_at") or 0.0),
            updated_at=float(raw.get("updated_at") or 0.0),
            saved_at=str(raw.get("saved_at") or ""),
        )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
  id         TEXT PRIMARY KEY,
  title      TEXT NOT NULL DEFAULT '',
  persona    TEXT NOT NULL DEFAULT 'orchestrator',
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  snapshot   TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS session_meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class SessionStore:
    """SQLite-backed persistence for chat sessions (one row each)."""

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        # Floor for strictly-increasing updated_at: wall clocks (Windows ~15ms
        # resolution) let two writes inside one tick share a timestamp, which
        # would make "most recently updated first" order nondeterministic.
        # Set before the legacy migration because it writes rows too.
        row = self._conn.execute("SELECT MAX(updated_at) FROM sessions").fetchone()
        self._ts_floor = float(row[0]) if row and row[0] else 0.0
        self._migrate_legacy()

    def _next_ts(self, now: float) -> float:
        ts = max(now, self._ts_floor + 1e-6)
        self._ts_floor = ts
        return ts

    # -- legacy migration ---------------------------------------------------

    def _migrate_legacy(self) -> None:
        """Copy the pre-multi-session single row (table `session`, key="chat")
        into a real session; the legacy table is kept untouched. Failure to
        migrate never blocks startup - the old row just stays legacy."""
        try:
            tables = {
                r[0]
                for r in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if _LEGACY_TABLE not in tables or self.get(_DEFAULT_SESSION_ID) is not None:
                return
            row = self._conn.execute(
                f"SELECT value FROM {_LEGACY_TABLE} WHERE key = 'chat'"
            ).fetchone()
            if row is None:
                return
            try:
                raw = json.loads(row[0])
            except ValueError:
                return
            snap = SessionSnapshot.from_dict(
                {
                    "session_id": _DEFAULT_SESSION_ID,
                    "title": raw.get("title") or "默认会话",
                    "persona": raw.get("persona") or "orchestrator",
                    "goal": raw.get("goal") or "",
                    "history": raw.get("history") or [],
                    "active_tools": raw.get("active_tools") or [],
                }
            )
            self.save(snap)
            self.set_active(_DEFAULT_SESSION_ID)
        except sqlite3.DatabaseError:
            return

    # -- row CRUD -----------------------------------------------------------

    def create(self, session_id: str, title: str, persona: str = "orchestrator") -> SessionSnapshot:
        """Insert a new session row; ids must match the strict pattern."""
        if not _valid_session_id(session_id):
            raise ValueError(f"invalid session id: {session_id!r}")
        now = time.time()
        snap = SessionSnapshot(
            session_id=session_id,
            title=title,
            persona=persona,
            created_at=now,
            updated_at=now,
            saved_at=datetime.now(UTC).isoformat(),
        )
        self.save(snap)
        return snap

    def save(self, snap: SessionSnapshot) -> None:
        """Upsert one session row (persisted after each chat turn)."""
        now = time.time()
        created = snap.created_at or now
        updated = snap.updated_at or self._next_ts(now)
        self._conn.execute(
            "INSERT INTO sessions (id, title, persona, created_at, updated_at, snapshot)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET title=excluded.title,"
            " persona=excluded.persona, updated_at=excluded.updated_at,"
            " snapshot=excluded.snapshot",
            (
                snap.session_id,
                snap.title,
                snap.persona,
                created,
                updated,
                json.dumps(snap.to_dict(), ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def get(self, session_id: str) -> SessionSnapshot | None:
        """Return one session; None when absent or corrupt."""
        try:
            row = self._conn.execute(
                "SELECT snapshot FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        except sqlite3.DatabaseError:
            return None
        if row is None:
            return None
        try:
            return SessionSnapshot.from_dict(json.loads(row[0]))
        except (ValueError, TypeError):
            return None

    def list(self) -> list[SessionMeta]:
        """All sessions, most recently updated first; corrupt rows are
        skipped so one bad record never hides the rest."""
        out: list[SessionMeta] = []
        try:
            rows = self._conn.execute(
                # rowid tie-break: two saves inside one clock tick share updated_at,
                # and the later insert must still sort first (deterministic listing)
                "SELECT id, title, persona, created_at, updated_at FROM sessions"
                " ORDER BY updated_at DESC, rowid DESC"
            ).fetchall()
        except sqlite3.DatabaseError:
            return out
        for r in rows:
            try:
                out.append(
                    SessionMeta(
                        session_id=str(r[0]),
                        title=str(r[1]),
                        persona=str(r[2]),
                        created_at=float(r[3]),
                        updated_at=float(r[4]),
                    )
                )
            except (TypeError, ValueError):
                continue
        return out

    def touch(self, session_id: str) -> None:
        """Bump updated_at without a full snapshot rewrite."""
        self._conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (self._next_ts(time.time()), session_id),
        )
        self._conn.commit()

    def rename(self, session_id: str, title: str) -> None:
        snap = self.get(session_id)
        if snap is None:
            return
        self.save(
            SessionSnapshot(
                session_id=snap.session_id,
                title=title,
                persona=snap.persona,
                goal=snap.goal,
                history=snap.history,
                active_tools=snap.active_tools,
                created_at=snap.created_at,
                updated_at=time.time(),
                saved_at=snap.saved_at,
            )
        )

    def delete(self, session_id: str) -> None:
        self._conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self._conn.commit()

    # -- active pointer ------------------------------------------------------

    def get_active(self) -> str:
        """Active session id; empty when unset (fresh store)."""
        try:
            row = self._conn.execute(
                "SELECT value FROM session_meta WHERE key = 'active'"
            ).fetchone()
        except sqlite3.DatabaseError:
            return ""
        return str(row[0]) if row else ""

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO session_meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._conn.commit()

    def get_meta(self, key: str) -> str:
        row = self._conn.execute("SELECT value FROM session_meta WHERE key = ?", (key,)).fetchone()
        return str(row[0]) if row else ""

    def meta_by_value(self, prefix: str, value: str) -> builtins.list[str]:
        """Keys whose value matches, among keys with the given prefix (used to
        list sessions forked from one parent)."""
        rows = self._conn.execute(
            "SELECT key FROM session_meta WHERE key LIKE ? AND value = ?",
            (prefix + "%", value),
        ).fetchall()
        return [str(r[0]) for r in rows]

    def meta_entries(self, prefix: str) -> dict[str, str]:
        """All key/value pairs whose key starts with prefix (boot scans use
        this to find persisted goals without listing sessions)."""
        rows = self._conn.execute(
            "SELECT key, value FROM session_meta WHERE key LIKE ?", (prefix + "%",)
        ).fetchall()
        return {str(k): str(v) for k, v in rows}

    def set_active(self, session_id: str) -> None:
        self._conn.execute(
            "INSERT INTO session_meta (key, value) VALUES ('active', ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (session_id,),
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


__all__ = ["SessionMeta", "SessionSnapshot", "SessionStore"]
