"""Write journal: content-addressed backup behind the fs write tools, so an
erroneous write/edit/delete can be rolled back without git.

One SQLite index plus a blob directory (dedup by sha256). The write tools
call capture() right before their first mutation and finalize() after it;
both are best-effort - a journal failure must never break the write path.

Undo safety rule: an entry is only restored when the file is in exactly the
state this journal saw after the write (post_sha match, or absent for
deletes). A file changed since the write is reported and skipped, never
overwritten with a stale restore.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class JournalEntry:
    seq: int
    ts: float
    path: str
    op: str  # write | create | delete
    pre_sha: str | None
    post_sha: str | None
    blob: str | None
    undone: bool


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class WriteJournal:
    def __init__(self, root: Path) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self._blobs = root / "blobs"
        self._blobs.mkdir(exist_ok=True)
        # Sync tool handlers run in worker threads (asyncio.to_thread), so the
        # journal is genuinely cross-thread: one lock serializes blob + index
        # mutations (invoke runs write tools sequentially, but not on one thread).
        self._lock = threading.Lock()
        self._db = sqlite3.connect(root / "journal.db", check_same_thread=False)
        self._db.execute(
            """CREATE TABLE IF NOT EXISTS writes (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                path TEXT NOT NULL,
                op TEXT NOT NULL,
                pre_sha TEXT,
                post_sha TEXT,
                blob TEXT,
                undone INTEGER NOT NULL DEFAULT 0
            )"""
        )
        self._db.commit()

    def close(self) -> None:
        """Release the sqlite connection (app shutdown / test teardown)."""
        with self._lock:
            self._db.close()

    def capture(self, path: Path, intent: str) -> int | None:
        """Snapshot the file's current content before a mutation; returns the
        entry id or None when the file state makes journaling moot (write of
        a not-yet-existing file still journals as create, with no blob)."""
        try:
            with self._lock:
                op = "delete" if intent == "delete" else ("write" if path.exists() else "create")
                blob = None
                pre_sha = None
                if op != "create":
                    data = path.read_bytes()
                    pre_sha = _sha(data)
                    blob = f"{pre_sha}.bin"
                    (self._blobs / blob).write_bytes(data)
                cur = self._db.execute(
                    "INSERT INTO writes (ts, path, op, pre_sha, blob) VALUES (?, ?, ?, ?, ?)",
                    (time.time(), str(path), op, pre_sha, blob),
                )
                self._db.commit()
                rowid = cur.lastrowid
                return int(rowid) if rowid is not None else None
        except Exception:  # noqa: BLE001  # journaling must never break the write path
            return None

    def finalize(self, entry: int | None, path: Path) -> None:
        """Record the content hash after the write (read-back), enabling the
        undo safety check; best-effort."""
        if entry is None:
            return
        try:
            with self._lock:
                post_sha = _sha(path.read_bytes()) if path.exists() else None
                self._db.execute("UPDATE writes SET post_sha = ? WHERE seq = ?", (post_sha, entry))
                self._db.commit()
        except Exception:  # noqa: BLE001
            return

    def recent(self, limit: int = 10) -> list[JournalEntry]:
        with self._lock:
            rows = self._db.execute(
                "SELECT seq, ts, path, op, pre_sha, post_sha, blob, undone FROM writes "
                "ORDER BY seq DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [JournalEntry(r[0], r[1], r[2], r[3], r[4], r[5], r[6], bool(r[7])) for r in rows]

    def undo(self, count: int = 1) -> dict:
        """Roll back the last `count` not-yet-undone write entries, newest
        first. Returns a per-entry summary; entries whose file changed since
        the write are skipped (never overwritten with a stale restore)."""
        with self._lock:
            rows = self._db.execute(
                "SELECT seq, path, op, pre_sha, post_sha, blob FROM writes "
                "WHERE undone = 0 ORDER BY seq DESC LIMIT ?",
                (count,),
            ).fetchall()
        results: list[dict] = []
        for seq, path_s, op, _pre_sha, post_sha, blob in rows:
            path = Path(path_s)
            outcome = self._restore(path, op, post_sha, blob)
            if outcome.startswith("restored"):
                with self._lock:
                    self._db.execute("UPDATE writes SET undone = 1 WHERE seq = ?", (seq,))
                    self._db.commit()
            results.append({"seq": seq, "path": path_s, "op": op, "result": outcome})
        return {"undone": len(results), "entries": results}

    def _restore(self, path: Path, op: str, post_sha: str | None, blob: str | None) -> str:
        try:
            if op == "delete":
                if path.exists():
                    return "skipped: path re-occupied after delete"
                if blob is None:
                    return "skipped: no backup content"
                path.write_bytes((self._blobs / blob).read_bytes())
                return "restored deleted file"
            current = path.read_bytes() if path.exists() else None
            current_sha = _sha(current) if current is not None else None
            if current_sha != post_sha:
                return "skipped: file changed after this write"
            if op == "create":
                if blob is not None:  # inconsistent entry: refuse to delete
                    return "skipped: create entry carries backup"
                path.unlink()
                return "removed created file"
            if blob is None:
                return "skipped: no backup content"
            path.write_bytes((self._blobs / blob).read_bytes())
            return "restored previous content"
        except FileNotFoundError:
            return "skipped: backup blob missing"
        except OSError as exc:
            return f"skipped: {exc}"


def safe_capture(journal: WriteJournal | None, path: Path, intent: str) -> int | None:
    """Call-site guard for the injected journal: a misbehaving collaborator
    must never break the write path (WriteJournal already guards internally;
    this covers foreign implementations)."""
    if journal is None:
        return None
    try:
        return journal.capture(path, intent)
    except Exception:  # noqa: BLE001
        return None


def safe_finalize(journal: WriteJournal | None, entry: int | None, path: Path) -> None:
    if journal is None or entry is None:
        return
    try:
        journal.finalize(entry, path)
    except Exception:  # noqa: BLE001
        return


__all__ = ["JournalEntry", "WriteJournal", "safe_capture", "safe_finalize"]
