"""Semantic memory: fact triples, optionally linked to graph nodes via
node_id (stored only, no graph queries here).

Responsibilities:
- SQLite-backed fact store (subject/relation/object plus optional node_id link)
- query() with matching-based multi-term scoring when candidates exceed
  limit, otherwise newest-first; purge()/clear() for retention
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from agent.memory.matching import like_pattern, score, split_terms

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ts       REAL NOT NULL,
    subject  TEXT NOT NULL,
    relation TEXT NOT NULL,
    object   TEXT NOT NULL,
    source   TEXT NOT NULL DEFAULT '',
    node_id  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject);
"""


class SemanticMemory:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def add(
        self,
        subject: str,
        relation: str,
        obj: str,
        *,
        source: str = "",
        node_id: str = "",
        supersede: bool = False,
    ) -> int:
        """Insert one fact triple. With supersede=True, older facts sharing the
        same (subject, relation) and the same source but a different object are
        deleted first — a distilled "X uses v2" replaces the earlier "X uses v1"
        instead of both surviving and competing for the same recall budget.
        Only same-source rows are replaced, so facts from other writers
        (user ratings, tool writes) are never touched."""
        with self._lock:
            if supersede:
                self._conn.execute(
                    "DELETE FROM facts WHERE subject = ? AND relation = ?"
                    " AND object <> ? AND source = ?",
                    (subject, relation, obj, source),
                )
            cur = self._conn.execute(
                "INSERT INTO facts (ts, subject, relation, object, source, node_id)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), subject, relation, obj, source, node_id),
            )
            self._conn.commit()
        if cur.lastrowid is None:  # unreachable: an INSERT always yields a rowid
            raise RuntimeError("insert produced no rowid")
        return int(cur.lastrowid)

    def has_fact(self, subject: str, relation: str, obj: str) -> bool:
        """Whether an identical triple already exists (exact match); lets the
        distiller skip re-writing a fact it previously extracted."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM facts WHERE subject = ? AND relation = ? AND object = ? LIMIT 1",
                (subject, relation, obj),
            )
            return cur.fetchone() is not None

    def query(
        self,
        *,
        subject: str | None = None,
        relation: str | None = None,
        keyword: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        sql = "SELECT id, ts, subject, relation, object, source, node_id FROM facts"
        conds: list[str] = []
        params: list[Any] = []
        terms: list[str] = []
        if subject:
            conds.append("subject = ?")
            params.append(subject)
        if relation:
            conds.append("relation = ?")
            params.append(relation)
        if keyword:
            # Multi-term scored search: split on whitespace, OR-fetch candidates
            # per term in SQL (capped at 200 rows), narrow by hit count in
            # Python; single-term behavior matches the old whole-string LIKE
            terms = split_terms(keyword)
            if terms:
                cols = ("subject", "object")
                kw_conds = " OR ".join(f"({c} LIKE ? ESCAPE '\\')" for t in terms for c in cols)
                conds.append(f"({kw_conds})")
                params.extend(like_pattern(t) for t in terms for _ in cols)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        # Reads and writes share the lock (recall_memory is a sync handler, so
        # it reads on a worker thread; concurrent writers must not interleave)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(
            200
        )  # candidate-pool cap: multi-term scoring needs candidates fetched before ranking
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        if terms and len(rows) > limit:
            scored = [(score(terms, [r[2], r[4]]), int(r[0]), r) for r in rows]
            scored.sort(key=lambda item: (-item[0], -item[1]))
            rows = [r for _, _, r in scored[:limit]]
        else:
            rows = rows[:limit]
        return [
            dict(zip(("id", "ts", "subject", "relation", "object", "source", "node_id"), r))
            for r in rows
        ]

    def purge(self, older_than_days: int) -> int:
        """Retention cleanup: remove facts older than the cutoff, returning the
        count removed."""
        cutoff = time.time() - older_than_days * 86400
        with self._lock:
            cur = self._conn.execute("DELETE FROM facts WHERE ts < ?", (cutoff,))
            self._conn.commit()
        return cur.rowcount

    def clear(self) -> int:
        """Wipe all fact triples (settings-page clear action), returning the
        count removed."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM facts")
            self._conn.commit()
        return cur.rowcount

    def close(self) -> None:
        self._conn.close()
