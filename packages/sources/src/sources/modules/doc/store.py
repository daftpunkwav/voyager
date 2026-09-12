"""Doc submodule data access: document metadata plus parsed section text.

documents carries the import lifecycle (importing/parsing/ready/stored/
failed); document_sections holds the parse pipeline output (section ->
page range -> text), fetched on demand.
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
CREATE TABLE IF NOT EXISTS documents (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    filename    TEXT NOT NULL DEFAULT '',
    ext         TEXT NOT NULL DEFAULT '',
    local_path  TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT '[]',
    progress    TEXT NOT NULL DEFAULT 'none',
    note        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'importing',
    error       TEXT NOT NULL DEFAULT '',
    source      TEXT NOT NULL DEFAULT 'manual',
    added_ts    REAL NOT NULL,
    updated_ts  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(status);
CREATE TABLE IF NOT EXISTS document_sections (
    doc_id     TEXT NOT NULL,
    section_no INTEGER NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    page_start INTEGER NOT NULL DEFAULT 0,
    page_end   INTEGER NOT NULL DEFAULT 0,
    text       TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (doc_id, section_no)
);
"""

_COLS = (
    "id",
    "title",
    "filename",
    "ext",
    "local_path",
    "category",
    "tags",
    "progress",
    "note",
    "status",
    "error",
    "source",
    "added_ts",
    "updated_ts",
)

#: List/detail summaries omit internal error details; section text is
#: fetched on demand only via get_doc_section
_SUMMARY_COLS = _COLS

_SORTABLE = {"added": "added_ts", "updated": "updated_ts", "title": "title"}


class DocStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        # RLock: search_summaries/summaries re-enter the internal read
        # methods; readers and writers share one lock (single-lock discipline)
        self._lock = threading.RLock()

    # ---------- Metadata ----------

    def add(self, doc: dict[str, Any]) -> str:
        did = doc.get("id") or uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO documents (id, title, filename, ext, local_path,"
                " category, tags, progress, note, status, error, source,"
                " added_ts, updated_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?)",
                (
                    did,
                    doc["title"],
                    doc.get("filename", ""),
                    doc.get("ext", ""),
                    doc.get("local_path", ""),
                    doc.get("category", ""),
                    json.dumps(doc.get("tags", []), ensure_ascii=False),
                    doc.get("progress", "none"),
                    doc.get("note", ""),
                    doc.get("status", "importing"),
                    doc.get("source", "manual"),
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return did

    def _fetch(
        self, where: str = "", params: tuple = (), order: str = "added_ts DESC"
    ) -> list[dict[str, Any]]:
        sql = f"SELECT {','.join(_SUMMARY_COLS)} FROM documents"
        if where:
            sql += f" WHERE {where}"
        rows = self._conn.execute(f"{sql} ORDER BY {order}", params).fetchall()
        return [_row(r) for r in rows]

    def get(self, did: str) -> dict[str, Any] | None:
        with self._lock:
            rows = self._fetch("id = ?", (did,))
        return rows[0] if rows else None

    def list(
        self,
        *,
        status: str = "",
        tag: str = "",
        query: str = "",
        sort: str = "added",
        desc: bool = True,
        limit: int = 200,
    ) -> builtins.list[dict[str, Any]]:
        wheres: builtins.list[str] = []
        params: builtins.list[Any] = []
        if status:
            wheres.append("status = ?")
            params.append(status)
        if tag:
            # tags is a JSON-array string: match with quotes as a whole term
            # to avoid substring false hits
            wheres.append(r"tags LIKE ? ESCAPE '\'")
            params.append(f"%{escape_like(tag)}%")
        if query:
            wheres.append("(title LIKE ? ESCAPE '\\' OR filename LIKE ? ESCAPE '\\')")
            like = f"%{escape_like(query)}%"
            params += [like, like]
        col = _SORTABLE.get(sort, "added_ts")
        order = f"{col} {'DESC' if desc else 'ASC'}"
        sql = f"SELECT {','.join(_SUMMARY_COLS)} FROM documents"
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += f" ORDER BY {order} LIMIT ?"
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row(r) for r in rows]

    def set_meta(self, did: str, **fields: Any) -> None:
        allowed = {"category", "tags", "progress", "note", "title"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        sets, params = [], []
        for k, v in updates.items():
            sets.append(f"{k} = ?")
            params.append(json.dumps(v, ensure_ascii=False) if k == "tags" else v)
        params += [time.time(), did]
        with self._lock:
            self._conn.execute(
                f"UPDATE documents SET {', '.join(sets)}, updated_ts = ? WHERE id = ?",
                params,
            )
            self._conn.commit()

    def set_status(self, did: str, status: str, *, error: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE documents SET status = ?, error = ?, updated_ts = ? WHERE id = ?",
                (status, error, time.time(), did),
            )
            self._conn.commit()

    def remove(self, did: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM documents WHERE id = ?", (did,))
            self._conn.execute("DELETE FROM document_sections WHERE doc_id = ?", (did,))
            self._conn.commit()

    # ---------- Parse output (sections) ----------

    def replace_sections(self, did: str, sections: builtins.list[dict[str, Any]]) -> None:
        """Replace the full section set in one pass (after a successful parse)."""
        with self._lock:
            self._conn.execute("DELETE FROM document_sections WHERE doc_id = ?", (did,))
            self._conn.executemany(
                "INSERT INTO document_sections"
                " (doc_id, section_no, title, page_start, page_end, text)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        did,
                        s["section_no"],
                        s.get("title", ""),
                        int(s.get("page_start", 0)),
                        int(s.get("page_end", 0)),
                        s.get("text", ""),
                    )
                    for s in sections
                ],
            )
            self._conn.commit()

    def sections_outline(self, did: str) -> builtins.list[dict[str, Any]]:
        """Outline: section number/title/page range only, no body text."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT section_no, title, page_start, page_end"
                " FROM document_sections WHERE doc_id = ? ORDER BY section_no",
                (did,),
            ).fetchall()
        return [dict(zip(("section_no", "title", "page_start", "page_end"), r)) for r in rows]

    def section(self, did: str, section_no: int) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT section_no, title, page_start, page_end, text"
                " FROM document_sections WHERE doc_id = ? AND section_no = ?",
                (did, section_no),
            ).fetchone()
        if row is None:
            return None
        return dict(zip(("section_no", "title", "page_start", "page_end", "text"), row))

    def sections_count(self, did: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM document_sections WHERE doc_id = ?",
                (did,),
            ).fetchone()
        return int(row[0])

    def search_sections(self, query: str, limit: int = 20) -> builtins.list[dict[str, Any]]:
        """Section full-text search: hits carry section no and snippet
        (LIKE-based, no relevance ranking).
        """
        like = f"%{escape_like(query)}%"
        with self._lock:
            rows = self._conn.execute(
                "SELECT s.doc_id, d.title, s.section_no, s.title, s.text"
                " FROM document_sections s JOIN documents d ON d.id = s.doc_id"
                " WHERE s.text LIKE ? ESCAPE '\\' ORDER BY d.added_ts DESC LIMIT ?",
                (like, limit),
            ).fetchall()
        out = []
        for doc_id, doc_title, section_no, sec_title, text in rows:
            pos = text.lower().find(query.lower())
            start = max(0, pos - 60)
            snippet = text[start : start + 200]
            out.append(
                {
                    "doc_id": doc_id,
                    "title": doc_title,
                    "section_no": section_no,
                    "section_title": sec_title,
                    "snippet": snippet,
                }
            )
        return out

    def search_summaries(self, query: str, limit: int = 100) -> builtins.list[dict[str, Any]]:
        """Consumed by the aggregate search_sources: converts section hits
        into the unified summary shape.

        The outer lock guarantees that hit + summary form one consistent
        snapshot (RLock re-enters the internal read methods).
        """
        with self._lock:
            hits = self.search_sections(query, limit)
            out = []
            for hit in hits:
                doc = self.get(hit["doc_id"])
                if doc is None:
                    continue
                out.append(
                    {
                        "id": hit["doc_id"],
                        "kind": "doc",
                        "title": doc["title"],
                        "subtitle": (
                            f"Section {hit['section_no']}"
                            + (f" · {hit['section_title']}" if hit["section_title"] else "")
                        ),
                        "status": doc.get("status", "ready"),
                        "progress": doc.get("progress", "none"),
                        "tags": doc.get("tags", []),
                        "category": doc.get("category", ""),
                        "added_ts": doc.get("added_ts", 0.0),
                        "updated_ts": doc.get("updated_ts", 0.0),
                        "match": {"section_no": hit["section_no"], "snippet": hit["snippet"]},
                    }
                )
        return out

    def summaries(
        self, *, status: str = "", tag: str = "", query: str = "", limit: int = 200
    ) -> builtins.list[dict[str, Any]]:
        """Unified resource-stream summary (consumed by list_sources).

        Fields aligned across kinds; the kind label is set by this store.
        """
        with self._lock:
            rows = self.list(status=status, tag=tag, query=query, limit=limit)
        return [
            {
                "id": r["id"],
                "kind": "doc",
                "title": r["title"],
                "subtitle": r["filename"],
                "status": r["status"],
                "progress": r["progress"],
                "tags": r["tags"],
                "category": r["category"],
                "added_ts": r["added_ts"],
                "updated_ts": r["updated_ts"],
            }
            for r in rows
        ]

    def stats(self) -> dict[str, int]:
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            by_status = dict(
                self._conn.execute(
                    "SELECT status, COUNT(*) FROM documents GROUP BY status"
                ).fetchall()
            )
        return {
            "total": int(total),
            "importing": int(by_status.get("importing", 0)),
            "parsing": int(by_status.get("parsing", 0)),
            "stored": int(by_status.get("stored", 0)),
            "failed": int(by_status.get("failed", 0)),
        }

    def all_ids(self) -> builtins.list[str]:
        with self._lock:
            return [r[0] for r in self._conn.execute("SELECT id FROM documents").fetchall()]

    def close(self) -> None:
        self._conn.close()


def _row(r: tuple) -> dict[str, Any]:
    d = dict(zip(_SUMMARY_COLS, r))
    d["tags"] = json.loads(d.get("tags") or "[]")
    return d
