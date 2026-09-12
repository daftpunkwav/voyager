"""Data access for the office service: documents and slide decks in
one namespace.

Responsibilities:
- One documents table shared by both sub-domains (kind='doc'/'slides')
- CRUD over title/block-list documents with a thread lock (async handlers
  may write from other threads)
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    kind       TEXT NOT NULL,
    blocks     TEXT NOT NULL DEFAULT '[]',
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_docs_kind ON documents(kind);
"""

_COLS = ("id", "title", "kind", "blocks", "created_ts", "updated_ts")


class DocumentStore:
    """Single table for docs and decks; kind='doc'/'slides' distinguishes sub-domains."""

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def create(self, title: str, kind: str, blocks: list[dict] | None = None) -> dict[str, Any]:
        did = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO documents (id, title, kind, blocks, created_ts, updated_ts)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (did, title, kind, json.dumps(blocks or [], ensure_ascii=False), now, now),
            )
            self._conn.commit()
        created = self.get(did)
        if created is None:  # unreachable: the row was written above
            raise KeyError(did)
        return created

    def get(self, did: str) -> dict[str, Any] | None:
        # Reads take the same lock as writes: async handlers may write from other threads.
        with self._lock:
            row = self._conn.execute(
                f"SELECT {','.join(_COLS)} FROM documents WHERE id=?", (did,)
            ).fetchone()
        return _row(_COLS, row) if row else None

    def update(
        self, did: str, *, title: str | None = None, blocks: list[dict] | None = None
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        if title is not None:
            fields["title"] = title
        if blocks is not None:
            fields["blocks"] = json.dumps(blocks, ensure_ascii=False)
        if not fields:
            existing = self.get(did)
            if existing is None:
                raise KeyError(did)
            return existing
        sets = ", ".join(f"{k}=?" for k in fields)
        params = list(fields.values()) + [time.time(), did]
        with self._lock:
            self._conn.execute(f"UPDATE documents SET {sets}, updated_ts=? WHERE id=?", params)
            self._conn.commit()
        updated = self.get(did)
        if updated is None:
            # backstop: the capability layer (_require_doc) is the not-found path;
            # this only trips on a delete racing the update
            raise KeyError(did)
        return updated

    def list(self, kind: str = "", limit: int = 100) -> list[dict[str, Any]]:
        sql = f"SELECT {','.join(_COLS)} FROM documents"
        params: list[Any] = []
        if kind:
            sql += " WHERE kind=?"
            params.append(kind)
        sql += " ORDER BY updated_ts DESC LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row(_COLS, r) for r in rows]

    def delete(self, did: str) -> bool:
        with self._lock:
            n = self._conn.execute("DELETE FROM documents WHERE id=?", (did,)).rowcount
            self._conn.commit()
        return n > 0

    def close(self) -> None:
        self._conn.close()


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    d = dict(zip(cols, r))
    d["blocks"] = json.loads(d.get("blocks") or "[]")
    return d
