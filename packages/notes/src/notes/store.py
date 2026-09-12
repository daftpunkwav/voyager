"""Data access for the notes service: the full storage layer for
Markdown notes.

State model: pinned/archived/trashed_ts are independent columns that combine
into four views:
- active (default): not archived, not deleted;
- archived: not in the default list, still searchable/openable;
- trash: trashed_ts set (recoverable);
- all: everything.

Responsibilities:
- Version snapshots: content changes auto-insert the old text into
  note_versions, keeping the last N versions per settings;
- Wiki links: [[targets]] are resolved into the note_links table (dst=id)
  on write, enabling backlink queries. Targets match by exact id first,
  then by case-insensitive exact title; dangling links are not stored
  (known tradeoff: they do not appear in backlinks);
- Full-text search: escaped LIKE over title/content (sufficient for a
  personal notes volume; FTS5 is a future option);
- Migration: missing columns are detected via PRAGMA and added with ALTER,
  preserving existing data.
"""

from __future__ import annotations

import builtins
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Self

from .store_links import backlinks as link_backlinks
from .store_links import resolve_link_targets as link_resolve
from .store_links import sync_links as link_sync

# DOMAIN lives in the leaf domain.py, so validate can be imported top-level
# without an import cycle.
from .validate import validate_tag

_SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    content    TEXT NOT NULL DEFAULT '',
    tags       TEXT NOT NULL DEFAULT '[]',
    source_id  TEXT NOT NULL DEFAULT '',
    node_id    TEXT NOT NULL DEFAULT '',
    created_ts REAL NOT NULL,
    updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_source ON notes(source_id);
CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes(updated_ts);

CREATE TABLE IF NOT EXISTS note_versions (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id  TEXT NOT NULL,
    version  INTEGER NOT NULL,
    content  TEXT NOT NULL,
    ts       REAL NOT NULL,
    UNIQUE (note_id, version)
);
CREATE INDEX IF NOT EXISTS idx_versions_note ON note_versions(note_id, version DESC);

CREATE TABLE IF NOT EXISTS note_links (
    src TEXT NOT NULL,
    dst TEXT NOT NULL,
    PRIMARY KEY (src, dst)
);
CREATE INDEX IF NOT EXISTS idx_links_dst ON note_links(dst);
"""

_SUMMARY_COLS = (
    "id",
    "title",
    "tags",
    "source_id",
    "node_id",
    "archived",
    "pinned",
    "trashed_ts",
    "created_ts",
    "updated_ts",
    "excerpt",
)
_ALL_COLS = (
    "id",
    "title",
    "content",
    "tags",
    "source_id",
    "node_id",
    "archived",
    "pinned",
    "trashed_ts",
    "created_ts",
    "updated_ts",
)
_STATE_CONDS: dict[str, tuple[str, list[Any]]] = {
    "active": ("archived = 0 AND trashed_ts IS NULL", []),
    "archived": ("archived = 1 AND trashed_ts IS NULL", []),
    "trash": ("trashed_ts IS NOT NULL", []),
    "all": ("1=1", []),
}
_EXCERPT_LEN = 120


def _normalize(text: str) -> str:
    """Normalize all line endings to LF.

    CRLF from Windows clipboards/editors would otherwise shift content
    offsets, line numbers, and search windows; everything is normalized
    before storage.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


class NoteStore:
    def __init__(self, db_path: str | Path, *, history_keep: int = 20) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._lock = threading.Lock()
        self.history_keep = max(0, history_keep)

    # ---------- Migration ----------

    def _migrate(self) -> None:
        """In-place upgrade of older databases: ALTER TABLE adds missing columns
        (SQLite has no ADD COLUMN IF NOT EXISTS).
        """
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(notes)")}
        for ddl in (
            "ALTER TABLE notes ADD COLUMN archived INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE notes ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE notes ADD COLUMN trashed_ts REAL",
        ):
            name = ddl.split("ADD COLUMN ")[1].split()[0]
            if name not in cols:
                self._conn.execute(ddl)
        self._conn.commit()

    # ---------- Basic CRUD ----------

    def create(self, note: dict[str, Any]) -> str:
        nid = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO notes (id, title, content, tags, source_id, node_id,"
                " archived, pinned, trashed_ts, created_ts, updated_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, 0, 0, NULL, ?, ?)",
                (
                    nid,
                    note["title"],
                    _normalize(note.get("content", "")),
                    json.dumps(note.get("tags", []), ensure_ascii=False),
                    note.get("source_id", ""),
                    note.get("node_id", ""),
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return nid

    def get(self, nid: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                f"SELECT {','.join(_ALL_COLS)} FROM notes WHERE id = ?", (nid,)
            ).fetchone()
        return _full_row(row) if row else None

    def exists_by_title(self, title: str) -> str | None:
        """Latest non-trashed note id whose title matches exactly (case-insensitive).

        Used for link resolution.
        """
        with self._lock:
            return self._exists_by_title_locked(title)

    def _exists_by_title_locked(self, title: str) -> str | None:
        row = self._conn.execute(
            "SELECT id FROM notes"
            " WHERE lower(title)=lower(?) AND trashed_ts IS NULL"
            " ORDER BY updated_ts DESC LIMIT 1",
            (title,),
        ).fetchone()
        return row[0] if row else None

    def update(self, nid: str, **fields: Any) -> bool:
        """Field-level update. A content change snapshots the old text first;
        returns whether a record was hit.

        Keeps the most recent history_keep snapshots (0 disables history).
        """
        allowed = {"title", "content", "tags", "source_id", "node_id", "pinned", "archived"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return False
        if "content" in updates:
            updates["content"] = _normalize(updates["content"])
        sets, params = [], []
        new_content = None
        for k, v in updates.items():
            sets.append(f"{k} = ?")
            params.append(json.dumps(v, ensure_ascii=False) if k == "tags" else v)
            if k == "content":
                new_content = v
        with self._lock:
            old_content = None
            if new_content is not None and self.history_keep > 0:
                row = self._conn.execute(
                    "SELECT content FROM notes WHERE id = ?", (nid,)
                ).fetchone()
                old_content = row[0] if row else None
            cur = self._conn.execute(
                f"UPDATE notes SET {', '.join(sets)}, updated_ts = ? WHERE id = ?",
                (*params, time.time(), nid),
            )
            self._conn.commit()
            if old_content is not None and old_content != new_content:
                self._snapshot_locked(nid, old_content)
        return cur.rowcount > 0

    def delete(self, nid: str) -> None:
        """Hard delete (versions and links included). Soft delete goes through trash()."""
        with self._lock:
            self._delete_ids_locked([nid])

    def delete_many(self, nids: list[str]) -> None:
        """Hard-delete many notes (versions and links included)."""
        with self._lock:
            self._delete_ids_locked(nids)

    def _delete_ids_locked(self, nids: list[str]) -> None:
        if not nids:
            return
        placeholders = ",".join("?" * len(nids))
        self._conn.execute(f"DELETE FROM notes WHERE id IN ({placeholders})", nids)
        self._conn.execute(f"DELETE FROM note_versions WHERE note_id IN ({placeholders})", nids)
        self._conn.execute(
            f"DELETE FROM note_links WHERE src IN ({placeholders}) OR dst IN ({placeholders})",
            [*nids, *nids],
        )
        self._conn.commit()

    # ---------- State transitions ----------

    def trash(self, nid: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE notes SET trashed_ts = ?, updated_ts = ?"
                " WHERE id = ? AND trashed_ts IS NULL",
                (time.time(), time.time(), nid),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def restore(self, nid: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE notes SET trashed_ts = NULL, updated_ts = ? WHERE id = ?",
                (time.time(), nid),
            )
            self._conn.commit()
        return cur.rowcount > 0

    def purge_expired(self, older_than_days: int) -> list[str]:
        """Purge trash entries older than the retention window
        (days <= 0 means keep forever -> no-op).

        Returns the purged ids so callers can batch-purge attachments and
        emit aggregate events.
        """
        if older_than_days <= 0:
            return []
        cutoff = time.time() - older_than_days * 86400
        with self._lock:
            rows = self._conn.execute(
                "SELECT id FROM notes WHERE trashed_ts IS NOT NULL AND trashed_ts < ?",
                (cutoff,),
            ).fetchall()
            nids = [r[0] for r in rows]
            self._delete_ids_locked(nids)
        return nids

    # ---------- Listing and search ----------

    def list(
        self,
        *,
        source_id: str | None = None,
        tag: str = "",
        query: str = "",
        state: str = "active",
        sort: str = "updated_ts",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Summary list (state filter plus keyword search).

        When query hits the content, the excerpt is a context window around
        the first hit (matching GitHub/Obsidian search results) instead of a
        fixed prefix; notes whose title alone matches fall back to the first
        120 characters.
        """
        col = sort if sort in _SORTABLE else "updated_ts"
        direction = "ASC" if col == "title" else "DESC"
        state_sql, state_params = _STATE_CONDS.get(state, _STATE_CONDS["active"])
        conds = [state_sql]
        params: list[Any] = list(state_params)
        if source_id is not None:
            conds.append("source_id = ?")
            params.append(source_id)
        if tag:
            conds.append("tags LIKE ? ESCAPE '\\'")
            params.append(f"%{_like_escape(json.dumps(tag, ensure_ascii=False))}%")
        excerpt_sql = f"substr(content, 1, {_EXCERPT_LEN})"
        if query:
            # Binding order matters: the CASE placeholders in the SELECT head
            # come before the LIKE placeholders in WHERE.
            needle = query.lower()
            excerpt_sql = (
                "CASE WHEN instr(lower(content), lower(?)) > 0 THEN"
                " substr(content, MAX(1, instr(lower(content), lower(?)) - 60), 180)"
                f" ELSE substr(content, 1, {_EXCERPT_LEN}) END"
            )
            params.extend([needle, needle])
            pattern = f"%{_like_escape(query)}%"
            conds.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            params.extend([pattern, pattern])
        sql = (
            "SELECT id, title, tags, source_id, node_id, archived, pinned,"
            " trashed_ts, created_ts, updated_ts,"
            f" {excerpt_sql} AS excerpt"
            f" FROM notes WHERE {' AND '.join(conds)}"
        )
        sql += f" ORDER BY pinned DESC, {col} {direction} LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_summary_row(r) for r in rows]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            counts = list(
                self._conn.execute(
                    "SELECT archived, trashed_ts IS NOT NULL, COUNT(*)"
                    " FROM notes GROUP BY archived, trashed_ts IS NOT NULL"
                )
            )
            tags_rows = list(self._conn.execute("SELECT tags FROM notes WHERE trashed_ts IS NULL"))
        states = {"active": 0, "archived": 0, "trash": 0}
        for flag, has_trash, n in counts:
            key = "trash" if has_trash else ("archived" if flag else "active")
            states[key] = states.get(key, 0) + n
        tag_counts: dict[str, int] = {}
        for (tags_json,) in tags_rows:
            try:
                for t in json.loads(tags_json):
                    tag_counts[t] = tag_counts.get(t, 0) + 1
            except ValueError:
                continue
        top_tags = sorted(tag_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
        return {
            **states,
            "total": sum(states.values()),
            "tags": [{"tag": t, "count": c} for t, c in top_tags],
        }

    def all_tags(self) -> builtins.list[tuple[str, int]]:
        with self._lock:
            rows = list(self._conn.execute("SELECT tags FROM notes WHERE trashed_ts IS NULL"))
        counter: dict[str, int] = {}
        for (tags_json,) in rows:
            try:
                for t in json.loads(tags_json):
                    counter[t] = counter.get(t, 0) + 1
            except ValueError:
                continue
        return sorted(counter.items())

    def rename_tag(self, old: str, new: str) -> int:
        """Rename a tag globally: parse the JSON and replace exact elements,
        avoiding substring false positives.
        """
        old = validate_tag(old)
        new = validate_tag(new)
        updated = 0
        with self._lock:
            rows = list(
                self._conn.execute(
                    "SELECT id, tags FROM notes WHERE instr(tags, ?) > 0",
                    (json.dumps(old, ensure_ascii=False),),
                )
            )
            for nid, tags_json in rows:
                try:
                    tags = json.loads(tags_json)
                except ValueError:
                    continue
                if not isinstance(tags, list):
                    continue
                if old not in tags:
                    continue
                next_tags = [new if t == old else t for t in tags]
                self._conn.execute(
                    "UPDATE notes SET tags = ?, updated_ts = ? WHERE id = ?",
                    (json.dumps(next_tags, ensure_ascii=False), time.time(), nid),
                )
                updated += 1
            self._conn.commit()
        return updated

    # ---------- Version history ----------

    def _snapshot_locked(self, nid: str, content: str) -> None:
        next_version = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM note_versions WHERE note_id = ?",
            (nid,),
        ).fetchone()[0]
        self._conn.execute(
            "INSERT INTO note_versions (note_id, version, content, ts) VALUES (?, ?, ?, ?)",
            (nid, next_version, content, time.time()),
        )
        keep_from = next_version - self.history_keep
        if keep_from > 0:
            self._conn.execute(
                "DELETE FROM note_versions WHERE note_id = ? AND version <= ?", (nid, keep_from)
            )

    def list_versions(self, nid: str) -> builtins.list[dict[str, Any]]:
        with self._lock:
            rows = list(
                self._conn.execute(
                    "SELECT version, ts, content FROM note_versions"
                    " WHERE note_id = ? ORDER BY version DESC",
                    (nid,),
                )
            )
        return [{"version": r[0], "ts": r[1], "chars": len(r[2])} for r in rows]

    def get_version(self, nid: str, version: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT content, ts FROM note_versions WHERE note_id = ? AND version = ?",
                (nid, version),
            ).fetchone()
        return {"content": row[0], "ts": row[1]} if row else None

    # ---------- Wiki links ----------

    def resolve_link_targets(self, content: str) -> builtins.list[dict[str, Any]]:
        with self._lock:
            return link_resolve(self._conn, content, self._exists_by_title_locked)

    def sync_links(self, src_id: str, content: str) -> None:
        # Must pass the _locked variant: link_sync calls back exists_by_title
        # while holding this lock, and threading.Lock is not reentrant — using
        # the public method would deadlock writes containing [[titles]].
        with self._lock:
            link_sync(self._conn, src_id, content, self._exists_by_title_locked)

    def backlinks(self, nid: str, limit: int = 50) -> builtins.list[dict[str, Any]]:
        with self._lock:
            return link_backlinks(self._conn, nid, limit)

    # ---------- Lifecycle ----------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _summary_row(r: tuple) -> dict[str, Any]:
    d = dict(zip(_SUMMARY_COLS, r))
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["archived"] = bool(d["archived"])
    d["pinned"] = bool(d["pinned"])
    return d


def _full_row(row: tuple) -> dict[str, Any]:
    d = dict(zip(_ALL_COLS, row))
    d["tags"] = json.loads(d.get("tags") or "[]")
    d["archived"] = bool(d["archived"])
    d["pinned"] = bool(d["pinned"])
    return d


_SORTABLE = {"updated_ts", "created_ts", "title"}
