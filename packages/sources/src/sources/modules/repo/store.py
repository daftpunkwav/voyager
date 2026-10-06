"""Repo submodule data access.

category is a plain string field (list_categories reads DISTINCT values)
and tags a JSON array; the README is cached at import time instead of
being refetched on every request; status carries the import lifecycle
(importing/ready/failed).
"""

from __future__ import annotations

import builtins
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .._shared.text import escape_like

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id          TEXT PRIMARY KEY,
    owner       TEXT NOT NULL,
    name        TEXT NOT NULL,
    url         TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    stars       INTEGER NOT NULL DEFAULT 0,
    language    TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]',
    progress    TEXT NOT NULL DEFAULT 'none',
    note        TEXT NOT NULL DEFAULT '',
    local_path  TEXT NOT NULL DEFAULT '',
    readme      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'importing',
    error       TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'manual',
    added_ts    REAL NOT NULL,
    updated_ts  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_repos_status ON repos(status);
"""

_COLS = (
    "id",
    "owner",
    "name",
    "url",
    "description",
    "stars",
    "language",
    "category",
    "tags",
    "progress",
    "note",
    "local_path",
    "readme",
    "status",
    "error",
    "source",
    "added_ts",
    "updated_ts",
)

#: Lists return summaries by default; the README body is fetched on
#: demand via get_readme
_SUMMARY_COLS = tuple(c for c in _COLS if c != "readme")

# Plain-literal SELECT statements; the column lists are kept in lockstep
# with _COLS / _SUMMARY_COLS (which feed _row via zip), never widened to *.
# Each statement is one standalone adjacent-literal string — no runtime
# concatenation composes them, so scanners can verify the constant text.
_SQL_SUMMARY_HEAD = (
    "SELECT id, owner, name, url, description, stars, language, category,"
    " tags, progress, note, local_path, status, error, source, added_ts,"
    " updated_ts FROM repos"
)
_SQL_FULL_HEAD = (
    "SELECT id, owner, name, url, description, stars, language, category,"
    " tags, progress, note, local_path, readme, status, error, source,"
    " added_ts, updated_ts FROM repos"
)
_SQL_GET_BY_ID_FULL = (
    "SELECT id, owner, name, url, description, stars, language, category,"
    " tags, progress, note, local_path, readme, status, error, source,"
    " added_ts, updated_ts FROM repos WHERE id = ?"
)
_SQL_GET_BY_ID_SUMMARY = (
    "SELECT id, owner, name, url, description, stars, language, category,"
    " tags, progress, note, local_path, status, error, source, added_ts,"
    " updated_ts FROM repos WHERE id = ?"
)
_SQL_GET_BY_URL = (
    "SELECT id, owner, name, url, description, stars, language, category,"
    " tags, progress, note, local_path, status, error, source, added_ts,"
    " updated_ts FROM repos WHERE url = ?"
)

# One literal UPDATE per editable field: every value stays a bound parameter
# and no SET clause is ever assembled at runtime. The keys ARE the whitelist.
_META_UPDATE_SQL = {
    "category": "UPDATE repos SET category = ?, updated_ts = ? WHERE id = ?",
    "tags": "UPDATE repos SET tags = ?, updated_ts = ? WHERE id = ?",
    "progress": "UPDATE repos SET progress = ?, updated_ts = ? WHERE id = ?",
    "note": "UPDATE repos SET note = ?, updated_ts = ? WHERE id = ?",
}

_SORTABLE = {"name": "name", "stars": "stars", "added": "added_ts", "updated": "updated_ts"}


class RepoStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def add(self, repo: dict[str, Any]) -> str:
        """Register a repo, or re-import over an existing URL.

        On URL conflict only source-side fields (owner/name/description/
        stars/README/status) are updated; user-set category/tags/progress/
        note are preserved so a re-import never loses metadata. RETURNING
        yields the surviving row's id (the old row's id on conflict).
        """
        rid = repo.get("id") or uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "INSERT INTO repos (id, owner, name, url, description, stars,"
                " language, category, tags, progress, note, local_path, readme, status,"
                " error, source, added_ts, updated_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(url) DO UPDATE SET"
                " owner=excluded.owner, name=excluded.name,"
                " description=excluded.description, stars=excluded.stars,"
                " language=excluded.language, readme=excluded.readme,"
                " status=excluded.status, error=excluded.error,"
                " updated_ts=excluded.updated_ts"
                " RETURNING id",
                (
                    rid,
                    repo.get("owner", ""),
                    repo["name"],
                    repo["url"],
                    repo.get("description", ""),
                    int(repo.get("stars", 0)),
                    repo.get("language", ""),
                    repo.get("category", ""),
                    json.dumps(repo.get("tags", []), ensure_ascii=False),
                    repo.get("progress", "none"),
                    repo.get("note", ""),
                    repo.get("local_path", ""),
                    repo.get("readme", ""),
                    repo.get("status", "importing"),
                    repo.get("error", ""),
                    repo.get("source", "manual"),
                    now,
                    now,
                ),
            ).fetchone()
            self._conn.commit()
        return str(row[0])

    def get(self, rid: str, *, with_readme: bool = True) -> dict[str, Any] | None:
        # Readers and writers share the same lock
        sql = _SQL_GET_BY_ID_FULL if with_readme else _SQL_GET_BY_ID_SUMMARY
        with self._lock:
            row = self._conn.execute(sql, (rid,)).fetchone()
        return _row(_COLS if with_readme else _SUMMARY_COLS, row) if row else None

    def get_by_url(self, url: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(_SQL_GET_BY_URL, (url,)).fetchone()
        return _row(_SUMMARY_COLS, row) if row else None

    def list(
        self, *, sort: str = "added", desc: bool = True, category: str = ""
    ) -> builtins.list[dict[str, Any]]:
        col = _SORTABLE.get(sort, "added_ts")
        order = col + (" DESC" if desc else " ASC")
        sql = _SQL_SUMMARY_HEAD
        params: list[Any] = []
        if category:
            sql += " WHERE category = ?"
            params.append(category)
        sql += " ORDER BY " + order
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row(_SUMMARY_COLS, r) for r in rows]

    def categories(self) -> builtins.list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT DISTINCT category FROM repos WHERE category != '' ORDER BY category"
            ).fetchall()
        return [r[0] for r in rows]

    def summaries(
        self, *, status: str = "", tag: str = "", query: str = "", limit: int = 200
    ) -> builtins.list[dict[str, Any]]:
        """Unified resource-stream summary (consumed by list_sources).

        Fields aligned across kinds; the kind label is set by this store.
        """
        wheres: builtins.list[str] = []
        params: builtins.list[Any] = []
        if status:
            wheres.append("status = ?")
            params.append(status)
        if tag:
            wheres.append(r"tags LIKE ? ESCAPE '\'")
            params.append(f"%{escape_like(tag)}%")
        if query:
            wheres.append("(name LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
            like = f"%{escape_like(query)}%"
            params += [like, like]
        sql = _SQL_SUMMARY_HEAD
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY added_ts DESC LIMIT ?"
        params.append(limit)
        out = []
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        for r in rows:
            d = dict(zip(_SUMMARY_COLS, r))
            out.append(
                {
                    "id": d["id"],
                    "kind": "repo",
                    "title": d["name"],
                    "subtitle": d["description"],
                    "status": d["status"],
                    "progress": d["progress"],
                    "tags": json.loads(d["tags"] or "[]"),
                    "category": d["category"],
                    "added_ts": d["added_ts"],
                    "updated_ts": d["updated_ts"],
                }
            )
        return out

    def stats(self) -> dict[str, int]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0]
            by_status = dict(
                self._conn.execute("SELECT status, COUNT(*) FROM repos GROUP BY status").fetchall()
            )
        return {
            "total": int(total),
            "importing": int(by_status.get("importing", 0)),
            "failed": int(by_status.get("failed", 0)),
        }

    def set_meta(self, rid: str, **fields: Any) -> None:
        updates = {k: v for k, v in fields.items() if k in _META_UPDATE_SQL and v is not None}
        if not updates:
            return
        now = time.time()
        with self._lock:
            try:
                for k, v in updates.items():
                    value = json.dumps(v, ensure_ascii=False) if k == "tags" else v
                    self._conn.execute(_META_UPDATE_SQL[k], (value, now, rid))
                self._conn.commit()
            except BaseException:
                # A later field failing must not leave earlier fields to be
                # persisted by the next commit.
                self._conn.rollback()
                raise

    def set_status(self, rid: str, status: str, *, local_path: str = "", error: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE repos SET status = ?, local_path = COALESCE(NULLIF(?, ''),"
                " local_path), error = ?, updated_ts = ? WHERE id = ?",
                (status, local_path, error, time.time(), rid),
            )
            self._conn.commit()

    def fail_in_flight(self, error: str) -> int:
        """Startup crash recovery: rows stuck in 'importing' can only come
        from a hard kill — the clone queue is in-memory and no worker will
        ever pick them up again, so they would sit in 'importing' forever
        (never re-importable as ready, always shown as in-flight). Mark them
        failed; re-import is the retry path (the URL upsert preserves user
        metadata). Returns the affected row count."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE repos SET status = 'failed', error = ?, updated_ts = ?"
                " WHERE status = 'importing'",
                (error, time.time()),
            )
            self._conn.commit()
        return cur.rowcount

    def remove(self, rid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM repos WHERE id = ?", (rid,))
            self._conn.commit()

    def close(self) -> None:
        self._conn.close()


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    d = dict(zip(cols, r))
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d
