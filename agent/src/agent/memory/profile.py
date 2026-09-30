"""User profile and preferences: key-value; render() provides the profile
summary for context assembly.

Responsibilities:
- Key-value store for user profile/preferences (JSON values, upsert semantics)
- render() composes the profile summary consumed by context assembly;
  rendered_keys() reports the keys actually visible under the same cap
- Reentrant lock (render() calls all() internally) over one sqlite database
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Any

log = logging.getLogger("agent.memory.profile")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class ProfileMemory:
    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        # RLock: render() calls all() in combination, so reentrancy is required
        self._lock = threading.RLock()

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO profile (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
            self._conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM profile WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM profile WHERE key = ?", (key,))
            self._conn.commit()

    def all(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM profile ORDER BY key").fetchall()
        out: dict[str, Any] = {}
        for k, v in rows:
            try:
                out[k] = json.loads(v)
            except ValueError:
                # One corrupt row (disk damage / hand edit) degrades to its raw
                # text instead of killing the whole read path
                log.warning("profile key %r: corrupt JSON value; serving it as raw text", k)
                out[k] = v
        return out

    def clear(self) -> int:
        """Wipe all profile key-values (settings-page clear action), returning
        the count removed."""
        with self._lock:
            cur = self._conn.execute("DELETE FROM profile")
            self._conn.commit()
        return cur.rowcount

    def render(self, max_chars: int = 800) -> str:
        """Profile summary (the system prompt is injected with the summary, not
        the full data)."""
        with self._lock:
            data = self.all()
        if not data:
            return "(暂无用户画像)"
        text = "\n".join(f"- {k}: {v}" for k, v in data.items())
        return text if len(text) <= max_chars else text[:max_chars] + "…"

    def rendered_keys(self, max_chars: int = 800) -> AbstractSet[str]:
        """Keys whose lines render whole under the same character cap as
        render(): the exclusion set for the relevance layer, so only genuinely
        visible profile entries stop recall from repeating them. A line cut
        mid-way keeps its recall eligibility — the resident layer shows only a
        fragment of it, so dropping the recall hit would lose the information
        entirely."""
        if max_chars <= 0:
            return set()
        with self._lock:
            data = self.all()
        keys: set[str] = set()
        used = 0  # chars consumed by the lines already laid out (+1 joiner each)
        for k, v in data.items():
            line = f"- {k}: {v}"
            if used + len(line) <= max_chars:
                keys.add(k)
            used += len(line) + 1
        return keys

    def close(self) -> None:
        self._conn.close()
