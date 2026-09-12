"""One-shot migration from legacy books/news databases to doc/web (runs
only when the legacy files exist; idempotent).

books rows -> documents (the legacy data has no parse output, so status
is always 'stored'); news rows -> webpages (domain backfilled from url).
After migration the legacy file is renamed to *.bak -- user data is
never silently deleted and can be cleaned up after manual review.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .modules.doc.store import _SCHEMA as DOC_SCHEMA
from .modules.web.store import _SCHEMA as WEB_SCHEMA


def migrate_legacy_books_news(data_dir: str | Path) -> None:
    data_dir = Path(data_dir)
    _migrate_books(data_dir / "books.db", data_dir / "doc.db")
    _migrate_news(data_dir / "news.db", data_dir / "web.db")


def _migrate_books(old_path: Path, new_path: Path) -> None:
    if not old_path.is_file():
        return
    conn = sqlite3.connect(str(old_path))
    try:
        rows = conn.execute(
            "SELECT id, title, author, format, local_path, note, added_ts FROM books"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return
    conn.close()
    if not rows:
        old_path.rename(old_path.with_suffix(".db.bak"))
        return
    target = sqlite3.connect(str(new_path))
    target.executescript(DOC_SCHEMA)
    now = time.time()
    for bid, title, author, fmt, local_path, note, added_ts in rows:
        existing = target.execute("SELECT 1 FROM documents WHERE id = ?", (bid,)).fetchone()
        if existing:
            continue
        target.execute(
            "INSERT OR IGNORE INTO documents (id, title, filename, ext,"
            " local_path, note, status, source, added_ts, updated_ts)"
            " VALUES (?, ?, ?, ?, ?, ?, 'stored', 'migrated', ?, ?)",
            (
                bid,
                title,
                Path(local_path).name if local_path else "",
                fmt or "",
                local_path or "",
                note or "",
                added_ts or now,
                now,
            ),
        )
    target.commit()
    target.close()
    old_path.rename(old_path.with_suffix(".db.bak"))


def _migrate_news(old_path: Path, new_path: Path) -> None:
    if not old_path.is_file():
        return
    conn = sqlite3.connect(str(old_path))
    try:
        rows = conn.execute(
            "SELECT id, title, url, summary, content, added_ts FROM news"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return
    conn.close()
    if not rows:
        old_path.rename(old_path.with_suffix(".db.bak"))
        return
    target = sqlite3.connect(str(new_path))
    target.executescript(WEB_SCHEMA)
    now = time.time()
    from urllib.parse import urlparse

    for nid, title, url, summary, content, added_ts in rows:
        existing = target.execute("SELECT 1 FROM webpages WHERE id = ?", (nid,)).fetchone()
        if existing:
            continue
        domain = urlparse(url).hostname or "" if url else ""
        target.execute(
            "INSERT OR IGNORE INTO webpages (id, title, url, domain, summary,"
            " content, tags, category, meta, added_ts, updated_ts)"
            " VALUES (?, ?, ?, ?, ?, ?, '[]', '', ?, ?, ?)",
            (
                nid,
                title,
                url or "",
                domain,
                summary or "",
                content or "",
                json.dumps({"chars": len(content or "")}),
                added_ts or now,
                now,
            ),
        )
    target.commit()
    target.close()
    old_path.rename(old_path.with_suffix(".db.bak"))
