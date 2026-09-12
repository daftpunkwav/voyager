"""Note wiki-style links: [[target]] resolution/persistence and
backlink queries.

Responsibilities:
- resolve_link_targets: match [[targets]] by exact id, then by existing
  title; unmatched targets stay dangling (target_id=None)
- sync_links: persist note_links rows on content write
- backlinks: which notes link to a given note
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from typing import Any

_WIKI_LINK_RE = re.compile(r"\[\[([^\[\]|#\n]+)")
_EXCERPT_LEN = 120


def resolve_link_targets(
    conn: sqlite3.Connection,
    content: str,
    exists_by_title: Callable[[str], str | None],
) -> list[dict[str, Any]]:
    """Resolve [[targets]] into detail dicts (raw/target_id/title).

    A None target_id marks a dangling link; title is backfilled from the
    matched existing note when one is found.
    """
    raws: list[str] = []
    seen_raw: set[str] = set()
    for m in _WIKI_LINK_RE.finditer(content):
        raw = m.group(1).strip()
        if raw and raw not in seen_raw:
            seen_raw.add(raw)
            raws.append(raw)
    out: list[dict[str, Any]] = []
    by_title_cache: dict[str, str | None] = {}
    for raw in raws:
        dst_id: str | None = None
        row = conn.execute("SELECT id, title FROM notes WHERE id = ?", (raw,)).fetchone()
        if row is not None:
            dst_id, title = str(row[0]), str(row[1])
        else:
            if raw not in by_title_cache:
                by_title_cache[raw] = exists_by_title(raw)
            hit = by_title_cache[raw]
            if hit:
                dst_id = hit
                row = conn.execute("SELECT id, title FROM notes WHERE id = ?", (hit,)).fetchone()
                title = str(row[1]) if row else raw
            else:
                title = raw
        out.append({"raw": raw, "target_id": dst_id, "title": title if dst_id else None})
    return out


def sync_links(
    conn: sqlite3.Connection,
    src_id: str,
    content: str,
    exists_by_title: Callable[[str], str | None],
) -> None:
    """Persist resolved [[targets]]: delete old rows, then insert new ones.

    Dangling targets are not stored. The caller must hold the store lock.
    """
    resolved = {
        item["target_id"]
        for item in resolve_link_targets(conn, content, exists_by_title)
        if item["target_id"]
    }
    conn.execute("DELETE FROM note_links WHERE src = ?", (src_id,))
    conn.executemany(
        "INSERT OR IGNORE INTO note_links (src, dst) VALUES (?, ?)",
        [(src_id, dst) for dst in sorted(resolved)],
    )
    conn.commit()


def backlinks(conn: sqlite3.Connection, nid: str, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT s.id, s.title, substr(s.content, 1, ?), s.updated_ts"
        " FROM note_links l JOIN notes s ON s.id = l.src"
        " WHERE l.dst = ? AND s.trashed_ts IS NULL"
        " ORDER BY s.updated_ts DESC LIMIT ?",
        (_EXCERPT_LEN, nid, limit),
    )
    return [{"id": r[0], "title": r[1], "excerpt": r[2], "updated_ts": r[3]} for r in rows]
