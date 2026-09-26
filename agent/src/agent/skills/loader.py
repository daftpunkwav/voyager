"""Skill loading: a resident index (name + description) with full text on
demand.

Bad-file tolerance: a SKILL.md that fails to read (non-UTF-8 / IO error) is skipped per file
with a warning, so one bad file cannot take down the whole index -- the skill index is
consumed in every turn's context build (builder.index()) and users can edit workspace/skills,
so an unreadable file would otherwise render the agent unusable. Same loading-tolerance
discipline as the hooks loader and plugins manifest.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger("agent.skills.loader")


class SkillLoader:
    """Scan roots for <name>/SKILL.md; the index reads only title and first-line description;
    full text loads on demand."""

    def __init__(self, roots: list[str | Path]) -> None:
        self._roots = [Path(r) for r in roots]
        # Per-root scan cache: (fingerprint, entries) where the fingerprint is
        # the sorted (path, mtime) list of SKILL.md files. The index feeds the
        # system prompt's skill layer every turn; without the cache each render
        # re-reads every SKILL.md from disk. mtimes detect edits, creations and
        # deletions, so the cached bytes only go stale if the filesystem lies.
        self._scan_cache: dict[str, tuple[list[tuple[str, float]], list[dict[str, str]]]] = {}

    def add_root(self, root: str | Path) -> None:
        """Append a scan root (after plugin approval); deduplicated after resolve."""
        path = Path(root).resolve()
        if all(existing.resolve() != path for existing in self._roots):
            self._roots.append(path)

    def remove_root(self, root: str | Path) -> bool:
        """Remove a scan root (plugin hot-unload); returns False when absent."""
        path = Path(root).resolve()
        for i, existing in enumerate(self._roots):
            if existing.resolve() == path:
                del self._roots[i]
                return True
        return False

    def index(self) -> list[dict[str, str]]:
        """Index entries return only name + description; local absolute paths never leave
        the loader."""
        return [{"name": item["name"], "description": item["description"]} for item in self._scan()]

    def full_text(self, name: str) -> str:
        for item in self._scan():
            if item["name"] == name:
                try:
                    return Path(item["path"]).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as exc:
                    # Present at index time but broken at read time (deleted / re-encoded):
                    # raise with "unavailable" semantics so the caller (the skill tool's load action)
                    # reports it via an error message instead of crashing the turn
                    raise KeyError(
                        f"skill {name} failed to read: {exc} (see index() for all)"
                    ) from exc
        raise KeyError(f"unknown skill: {name} (see index() for all)")

    def _scan(self) -> list[dict[str, str]]:
        """Internal scan: includes path so full_text can read from disk on demand. Bad files
        are skipped with a warning. Per-root cached on the SKILL.md (path, mtime) set."""
        out: list[dict[str, str]] = []
        for root in self._roots:
            if not root.exists():
                continue
            files = sorted(root.rglob("SKILL.md"))
            fingerprint: list[tuple[str, float]] = []
            for p in files:
                try:
                    fingerprint.append((str(p), p.stat().st_mtime))
                except OSError:
                    fingerprint.append((str(p), -1.0))  # vanished mid-scan: re-read next time
            key = str(root)
            cached = self._scan_cache.get(key)
            if cached is not None and cached[0] == fingerprint:
                out.extend(cached[1])
                continue
            entries: list[dict[str, str]] = []
            for skill_md in files:
                description = self._read_desc(skill_md)
                if description is None:
                    continue  # bad file: already warned in _read_desc; kept out of the index
                entries.append(
                    {
                        "name": skill_md.parent.name,
                        "description": description,
                        "path": str(skill_md),
                    }
                )
            self._scan_cache[key] = (fingerprint, entries)
            out.extend(entries)
        return out

    @staticmethod
    def _read_desc(path: Path) -> str | None:
        """Read the first line as the description; return None on read failure (this function
        warns, the caller skips)."""
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            log.warning("skill %s unreadable, skipped: %s", path, exc)
            return None
        for line in text.splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                return line[:120]
        return ""
