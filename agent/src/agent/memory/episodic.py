"""Episodic memory: decision audit trail - trigger -> observation ->
judgment -> call -> result.

Responsibilities:
- SQLite-backed episode log (ts / run_id / kind / summary / detail JSON)
- recent()/search() with matching-based multi-term scoring for recall
- purge()/clear() for retention; reads and writes share one lock (cross-thread)
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from agent.memory.matching import like_pattern, score, split_terms

_SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      REAL NOT NULL,
    run_id  TEXT NOT NULL DEFAULT '',
    kind    TEXT NOT NULL,
    summary TEXT NOT NULL,
    detail  TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_episodes_ts ON episodes(ts);
CREATE INDEX IF NOT EXISTS idx_episodes_run ON episodes(run_id);
"""


class EpisodicMemory:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def log(
        self,
        kind: str,
        summary: str,
        detail: dict[str, Any] | None = None,
        *,
        run_id: str = "",
    ) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO episodes (ts, run_id, kind, summary, detail) VALUES (?, ?, ?, ?, ?)",
                (time.time(), run_id, kind, summary, json.dumps(detail or {}, ensure_ascii=False)),
            )
            self._conn.commit()
        if cur.lastrowid is None:  # unreachable: an INSERT always yields a rowid
            raise RuntimeError("insert produced no rowid")
        return int(cur.lastrowid)

    def recent(self, limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]:
        # Reads and writes share the lock (recall_memory is a sync handler, so
        # it reads on a worker thread; concurrent writers must not interleave)
        sql = "SELECT id, ts, run_id, kind, summary, detail FROM episodes"
        params: list[Any] = []
        if kind:
            sql += " WHERE kind = ?"
            params.append(kind)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row(r) for r in rows]

    def search(self, keyword: str, limit: int = 10) -> list[dict[str, Any]]:
        """Multi-term scored search: split on whitespace, OR-fetch candidates
        per term in SQL (capped at 200 rows), ranked by hit-term count desc
        then id desc; single-term queries behave like the old whole-string
        LIKE."""
        terms = split_terms(keyword)
        if not terms:
            return []
        cols = ("summary", "detail")
        conds = " OR ".join(f"({c} LIKE ? ESCAPE '\\')" for t in terms for c in cols)
        params = [like_pattern(t) for t in terms for _ in cols]
        sql = (
            "SELECT id, ts, run_id, kind, summary, detail FROM episodes"
            f" WHERE {conds} ORDER BY id DESC LIMIT 200"
        )
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for r in rows:
            row = _row(r)
            hits = score(terms, [row["summary"], json.dumps(row["detail"], ensure_ascii=False)])
            scored.append((hits, int(r[0]), row))
        scored.sort(key=lambda item: (-item[0], -item[1]))
        return [row for _, _, row in scored[:limit]]

    def count(self, kind: str | None = None) -> int:
        """Number of stored episodes (optionally of one kind); cadence input for
        the skill organizer."""
        sql = "SELECT COUNT(*) FROM episodes"
        params: list[Any] = []
        if kind:
            sql += " WHERE kind = ?"
            params.append(kind)
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return int(row[0]) if row else 0

    def purge(self, older_than_days: int) -> int:
        """Retention cleanup: remove episodes older than the cutoff, returning
        the count removed."""
        cutoff = time.time() - older_than_days * 86400
        with self._lock:
            cur = self._conn.execute("DELETE FROM episodes WHERE ts < ?", (cutoff,))
            self._conn.commit()
        return cur.rowcount

    def clear(self) -> int:
        """Wipe all episodes (settings-page clear action); unrelated to purge's
        retention semantics."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM episodes")
            self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()


def _row(r: tuple) -> dict[str, Any]:
    return {
        "id": r[0],
        "ts": r[1],
        "run_id": r[2],
        "kind": r[3],
        "summary": r[4],
        "detail": json.loads(r[5]),
    }
