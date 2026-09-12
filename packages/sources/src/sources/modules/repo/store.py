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

    def _fetch(
        self, where: str = "", params: tuple = (), cols=_SUMMARY_COLS, order: str = "added_ts DESC"
    ) -> list[dict[str, Any]]:
        sql = f"SELECT {','.join(cols)} FROM repos"
        if where:
            sql += f" WHERE {where}"
        rows = self._conn.execute(f"{sql} ORDER BY {order}", params).fetchall()
        return [_row(cols, r) for r in rows]

    def get(self, rid: str, *, with_readme: bool = True) -> dict[str, Any] | None:
        # Readers and writers share the same lock
        cols = _COLS if with_readme else _SUMMARY_COLS
        with self._lock:
            rows = self._fetch("id = ?", (rid,), cols=cols)
        return rows[0] if rows else None

    def get_by_url(self, url: str) -> dict[str, Any] | None:
        with self._lock:
            rows = self._fetch("url = ?", (url,))
        return rows[0] if rows else None

    def list(
        self, *, sort: str = "added", desc: bool = True, category: str = ""
    ) -> builtins.list[dict[str, Any]]:
        col = _SORTABLE.get(sort, "added_ts")
        where, params = ("category = ?", (category,)) if category else ("", ())
        with self._lock:
            return self._fetch(where, params, order=f"{col} {'DESC' if desc else 'ASC'}")

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
        sql = f"SELECT {','.join(_SUMMARY_COLS)} FROM repos"
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
        allowed = {"category", "tags", "progress", "note"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        sets, params = [], []
        for k, v in updates.items():
            sets.append(f"{k} = ?")
            params.append(json.dumps(v, ensure_ascii=False) if k == "tags" else v)
        params += [time.time(), rid]
        with self._lock:
            self._conn.execute(
                f"UPDATE repos SET {', '.join(sets)}, updated_ts = ? WHERE id = ?",
                params,
            )
            self._conn.commit()

    def set_status(self, rid: str, status: str, *, local_path: str = "", error: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE repos SET status = ?, local_path = COALESCE(NULLIF(?, ''),"
                " local_path), error = ?, updated_ts = ? WHERE id = ?",
                (status, local_path, error, time.time(), rid),
            )
            self._conn.commit()

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
