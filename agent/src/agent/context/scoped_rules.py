"""Directory-scoped rules: load the task root's AGENTS.md as an extra rule
layer (ecosystem convention, D-08).

Only the file directly under the given root is read, and only when it
resolves inside that root (a symlinked AGENTS.md pointing elsewhere is
ignored), so the jail boundary holds even though this is not a tool call.
Content is bounded and cached by mtime; a missing or unreadable file yields
an empty layer rather than an error.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("agent.context.scoped_rules")

RULES_FILENAME = "AGENTS.md"
_MAX_CHARS = 4000


class ScopedRules:
    def __init__(self, root: str | Path, *, max_chars: int = _MAX_CHARS) -> None:
        self._root = Path(root).resolve()
        self._max_chars = max_chars
        self._cache: tuple[tuple[int, int], str] | None = None  # ((mtime_ns, size), text)

    @property
    def path(self) -> Path:
        return self._root / RULES_FILENAME

    def render(self) -> str:
        """Rule text for the root, "" when absent; re-read only when the file
        changed (mtime or size)."""
        path = self.path
        try:
            resolved = path.resolve()
            if resolved.parent != self._root:
                return ""  # symlink escaping the root: not ours to read
            st = resolved.stat()
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            self._cache = None
            return ""
        # mtime alone can collide for two writes inside one filesystem tick;
        # pairing it with the size keeps the cache honest for quick rewrites
        if self._cache is not None and self._cache[0] == stamp:
            return self._cache[1]
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            log.warning("scoped rules unreadable: %s", path, exc_info=True)
            self._cache = None
            return ""
        if len(text) > self._max_chars:
            text = text[: self._max_chars] + "\n…[截断]"
        self._cache = (stamp, text)
        return text


__all__ = ["RULES_FILENAME", "ScopedRules"]
