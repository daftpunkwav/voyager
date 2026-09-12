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

    def _rows(
        self, cols: tuple[str, ...], where: str = "", params: tuple = (), limit: int | None = None
    ) -> list[dict[str, Any]]:
        sql = f"SELECT {','.join(cols)} FROM webpages"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY added_ts DESC"
        args: list[Any] = list(params)
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        return [_row(cols, r) for r in self._conn.execute(sql, args).fetchall()]

    def get(self, pid: str) -> dict[str, Any] | None:
        # Readers and writers share the same lock
        with self._lock:
            rows = self._rows(_COLS, "id = ?", (pid,))
        return rows[0] if rows else None

    def list(
        self, *, query: str = "", tag: str = "", limit: int = 50
    ) -> builtins.list[dict[str, Any]]:
        wheres, params = [], []
        if query:
            like = f"%{escape_like(query)}%"
            wheres.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            params += [like, like]
        if tag:
            wheres.append(r"tags LIKE ? ESCAPE '\'")
            params.append(f"%{escape_like(tag)}%")
        with self._lock:
            return self._rows(_LIST_COLS, " AND ".join(wheres), tuple(params), min(limit, 500))

    def set_meta(self, pid: str, **fields: Any) -> None:
        allowed = {"title", "tags", "category"}
        updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not updates:
            return
        sets, params = [], []
        for k, v in updates.items():
            sets.append(f"{k} = ?")
            params.append(json.dumps(v, ensure_ascii=False) if k == "tags" else v)
        params += [time.time(), pid]
        with self._lock:
            self._conn.execute(
                f"UPDATE webpages SET {', '.join(sets)}, updated_ts = ? WHERE id = ?",
                params,
            )
            self._conn.commit()

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
            params.append(f"%{escape_like(tag)}%")
        if query:
            like = f"%{escape_like(query)}%"
            wheres.append("(title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\')")
            params += [like, like]
        cols = _LIST_COLS + ("updated_ts",)
        sql = f"SELECT {','.join(cols)} FROM webpages"
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
    body = re.sub(r"</(?:p|div|li|h[1-6]|blockquote)>", "\n", body, flags=re.IGNORECASE)
    text = _TAG_RE.sub(" ", body)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return title, text[:limit], images
