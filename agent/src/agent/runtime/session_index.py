"""Session search projection: an SQLite FTS5 index over conversation text in
the event log (the log stays the source of truth).

One writer only: `catch_up()` folds user.message / agent.message rows after
the projection's own cursor into an FTS table. Re-running catch_up is
idempotent and a deleted index file simply rebuilds from the log; reads
never touch the log.

CJK tokenization: unicode61 keeps a run of Chinese characters as ONE token,
so substring queries never match. Indexed text is normalized by splitting
CJK characters into single tokens (ascii words stay whole); the raw text is
kept in an unindexed column and snippets are cut from it directly. Queries
are phrase-quoted with the same normalization, so model-supplied text can
never inject FTS grammar.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from platform_contracts import DomainEvent
from platform_eventbus import EventLog

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS hits USING fts5(
    session UNINDEXED,
    seq UNINDEXED,
    role UNINDEXED,
    ts UNINDEXED,
    raw UNINDEXED,
    text
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_SOURCE_TYPES = (DomainEvent.USER_MESSAGE, DomainEvent.AGENT_MESSAGE)

_ROLE_BY_TYPE = {
    DomainEvent.USER_MESSAGE: "user",
    DomainEvent.AGENT_MESSAGE: "assistant",
}

#: A CJK ideograph, or a run of ascii letters/digits (tokenization units)
_TERM_RE = re.compile(r"[0-9A-Za-z]+|[\u4e00-\u9fff]")

#: Query-time units: consecutive CJK stays one term (raw.find in snippets)
_QUERY_TERM_RE = re.compile(r"[0-9A-Za-z]+|[\u4e00-\u9fff]+")


def normalize(text: str) -> str:
    """Space-separate CJK characters (ascii words stay whole) so the default
    unicode61 tokenizer sees one token per character."""
    return " ".join(_TERM_RE.findall(text))


def phrase_quote(query: str) -> str:
    """Each term becomes one quoted phrase; phrases join with implicit AND.
    Only CJK characters and ascii words survive, so FTS grammar operators in
    model text are inert data."""
    terms = _QUERY_TERM_RE.findall(query)
    parts = ['"' + " ".join(_TERM_RE.findall(t)) + '"' for t in terms]
    return " ".join(parts)


def _snippet(raw: str, query: str, *, width: int = 100) -> str:
    """A window from the raw text around the first matching term; the head of
    the raw text when no term appears verbatim (e.g. punctuation splits)."""
    for term in _QUERY_TERM_RE.findall(query):
        i = raw.find(term)
        if i >= 0:
            lo, hi = max(0, i - 30), min(len(raw), i + len(term) + width - 30)
            return ("…" if lo else "") + raw[lo:hi] + ("…" if hi < len(raw) else "")
    return raw[:width]


class SessionIndex:
    def __init__(self, db_path: str | Path, log: EventLog) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()
        self._log = log

    def _cursor(self) -> int:
        row = self._conn.execute("SELECT value FROM meta WHERE key = 'cursor'").fetchone()
        return int(row[0]) if row else 0

    def catch_up(self) -> int:
        """Fold conversation events past the cursor; returns rows added."""
        with self._lock:
            cursor = self._cursor()
            rows = self._log.read_after(cursor, types=_SOURCE_TYPES, limit=2000)
            added = 0
            for seq, event in rows:
                payload = event.payload or {}
                text = str(payload.get("content") or "")
                session = str(payload.get("session") or "")
                if not text:
                    continue
                self._conn.execute(
                    "INSERT INTO hits (session, seq, role, ts, raw, text) VALUES (?,?,?,?,?,?)",
                    (
                        session,
                        seq,
                        _ROLE_BY_TYPE[event.type],
                        event.ts,
                        text,
                        normalize(text),
                    ),
                )
                added += 1
            if rows:
                self._conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('cursor', ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (str(rows[-1][0]),),
                )
                self._conn.commit()
            return added

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
        """Phrase-quoted FTS match, newest first; each hit carries a snippet
        cut from the raw text. Empty queries return nothing."""
        needle = (query or "").strip()
        if not needle:
            return []
        match = phrase_quote(needle)
        if not match:
            return []
        with self._lock:
            rows = self._conn.execute(
                "SELECT session, seq, role, ts, raw FROM hits WHERE hits MATCH ?"
                " ORDER BY seq DESC LIMIT ?",
                (match, max(1, min(int(limit), 50))),
            ).fetchall()
        return [
            {
                "session": r[0],
                "seq": r[1],
                "role": r[2],
                "ts": r[3],
                "snippet": _snippet(r[4], needle),
            }
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()


__all__ = ["SessionIndex", "normalize", "phrase_quote"]
