"""Web submodule data access: clipped web pages (fetched by URL or entered
manually).

content stores the extracted body text (structured into paragraphs),
never raw HTML; the domain/tags/meta columns support filtering and search.
"""

from __future__ import annotations

import builtins
import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

# Explicit re-export: the capabilities layer imports valid_tag through this
# module; __all__ pins it so linters do not drop it as an unused import
from .._shared.text import escape_like, valid_tag

__all__ = ["escape_like", "valid_tag"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS webpages (
    id        TEXT PRIMARY KEY,
    title     TEXT NOT NULL,
    url       TEXT NOT NULL DEFAULT '',
    domain    TEXT NOT NULL DEFAULT '',
    summary   TEXT NOT NULL DEFAULT '',
    content   TEXT NOT NULL DEFAULT '',
    tags      TEXT NOT NULL DEFAULT '[]',
    category  TEXT NOT NULL DEFAULT '',
    meta      TEXT NOT NULL DEFAULT '{}',
    added_ts  REAL NOT NULL,
    updated_ts REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pages_added ON webpages(added_ts);
"""

_COLS = (
    "id",
    "title",
    "url",
    "domain",
    "summary",
    "content",
    "tags",
    "category",
    "meta",
    "added_ts",
    "updated_ts",
)
_LIST_COLS = ("id", "title", "url", "domain", "summary", "tags", "category", "added_ts")

# Plain-literal SELECT heads; the column lists are kept in lockstep with
# _COLS / _LIST_COLS (which feed _row via zip), never widened to *.
_SQL_GET_PAGE = (
    "SELECT id, title, url, domain, summary, content, tags, category, meta,"
    " added_ts, updated_ts FROM webpages WHERE id = ?"
)
_SQL_LIST_HEAD = "SELECT id, title, url, domain, summary, tags, category, added_ts FROM webpages"
_SQL_SUMMARY_HEAD = (
    "SELECT id, title, url, domain, summary, tags, category, added_ts, updated_ts FROM webpages"
)

# One literal UPDATE per editable field: every value stays a bound parameter
# and no SET clause is ever assembled at runtime. The keys ARE the whitelist.
_META_UPDATE_SQL = {
    "title": "UPDATE webpages SET title = ?, updated_ts = ? WHERE id = ?",
    "tags": "UPDATE webpages SET tags = ?, updated_ts = ? WHERE id = ?",
    "category": "UPDATE webpages SET category = ?, updated_ts = ? WHERE id = ?",
}


class WebStore:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def add(self, item: dict[str, Any]) -> str:
        pid = uuid.uuid4().hex[:12]
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO webpages (id, title, url, domain, summary, content,"
                " tags, category, meta, added_ts, updated_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pid,
                    item["title"],
                    item.get("url", ""),
                    item.get("domain", ""),
                    item.get("summary", ""),
                    item.get("content", ""),
                    json.dumps(item.get("tags", []), ensure_ascii=False),
                    item.get("category", ""),
                    json.dumps(item.get("meta", {}), ensure_ascii=False),
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return pid

    def get(self, pid: str) -> dict[str, Any] | None:
        # Readers and writers share the same lock
        with self._lock:
            row = self._conn.execute(_SQL_GET_PAGE, (pid,)).fetchone()
        return _row(_COLS, row) if row else None

    def list(
        self, *, query: str = "", tag: str = "", limit: int = 50
    ) -> builtins.list[dict[str, Any]]:
        wheres: list[str] = []
        params: list[Any] = []
        if query:
            like = f"%{escape_like(query)}%"
            wheres.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            params += [like, like]
        if tag:
            # JSON-quote the term like the notes store: tag "ai" must not
            # hit "ai-tools" inside the stored JSON array
            wheres.append(r"tags LIKE ? ESCAPE '\'")
            params.append(f"%{escape_like(json.dumps(tag, ensure_ascii=False))}%")
        sql = _SQL_LIST_HEAD
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY added_ts DESC LIMIT ?"
        params.append(min(limit, 500))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_row(_LIST_COLS, r) for r in rows]

    def set_meta(self, pid: str, **fields: Any) -> None:
        updates = {k: v for k, v in fields.items() if k in _META_UPDATE_SQL and v is not None}
        if not updates:
            return
        now = time.time()
        with self._lock:
            try:
                for k, v in updates.items():
                    value = json.dumps(v, ensure_ascii=False) if k == "tags" else v
                    self._conn.execute(_META_UPDATE_SQL[k], (value, now, pid))
                self._conn.commit()
            except BaseException:
                # A later field failing must not leave earlier fields to be
                # persisted by the next commit.
                self._conn.rollback()
                raise

    def remove(self, pid: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM webpages WHERE id = ?", (pid,))
            self._conn.commit()

    def summaries(
        self, *, status: str = "", tag: str = "", query: str = "", limit: int = 200
    ) -> builtins.list[dict[str, Any]]:
        """Unified resource-stream summary (consumed by list_sources).

        Fields aligned across kinds; the kind label is set by this store.
        Pages have no import lifecycle (always ready), so any other status
        filter naturally matches nothing.
        """
        if status and status != "ready":
            return []
        wheres: builtins.list[str] = []
        params: builtins.list[Any] = []
        if tag:
            wheres.append(r"tags LIKE ? ESCAPE '\'")
            params.append(f"%{escape_like(json.dumps(tag, ensure_ascii=False))}%")
        if query:
            like = f"%{escape_like(query)}%"
            wheres.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            params += [like, like]
        cols = _LIST_COLS + ("updated_ts",)
        sql = _SQL_SUMMARY_HEAD
        if wheres:
            sql += " WHERE " + " AND ".join(wheres)
        sql += " ORDER BY added_ts DESC LIMIT ?"
        params.append(limit)
        out = []
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        for r in rows:
            d = dict(zip(cols, r))
            out.append(
                {
                    "id": d["id"],
                    "kind": "web",
                    "title": d["title"],
                    "subtitle": d["domain"],
                    "status": "ready",
                    "progress": "none",
                    "tags": json.loads(d["tags"] or "[]"),
                    "category": d["category"],
                    "added_ts": d["added_ts"],
                    "updated_ts": d["updated_ts"],
                }
            )
        return out

    def stats(self) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM webpages").fetchone()
        return {"total": int(row[0])}

    def close(self) -> None:
        self._conn.close()


def _row(cols: tuple[str, ...], r: tuple) -> dict[str, Any]:
    d = dict(zip(cols, r))
    if "tags" in d:
        d["tags"] = json.loads(d.get("tags") or "[]")
    if "meta" in d:
        d["meta"] = json.loads(d.get("meta") or "{}")
    return d


# ---------- Body extraction (html_to_text: paragraph structure + first images) ----------

_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.IGNORECASE)
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)


def html_to_text(html: str, limit: int = 20000) -> tuple[str, str, list[str]]:
    """Extract the body: returns (title, paragraph text, image URL list).

    Paragraph structuring: block-level tag boundaries become newlines,
    keeping the text readable and searchable.
    """
    m = _TITLE_RE.search(html)
    title = _TAG_RE.sub("", m.group(1)).strip() if m else ""
    images = [u for u in _IMG_RE.findall(html)[:5] if u.startswith(("http", "/"))]
    body = _SCRIPT_STYLE_RE.sub(" ", html)
    # Truncated pages: the paired-tag regex above only strips complete
    # blocks, so strip an unclosed <script>/<style> tail as well or its raw
    # JS/CSS leaks into the extracted text
    body = re.sub(r"<(script|style)\b[^>]*>.*", " ", body, flags=re.IGNORECASE | re.DOTALL)
    body = re.sub(r"</(?:p|div|li|h[1-6]|blockquote)>", "\n", body, flags=re.IGNORECASE)
    text = _TAG_RE.sub(" ", body)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return title, text[:limit], images
