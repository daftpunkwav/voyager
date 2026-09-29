"""Shared filesystem helpers for the sources submodules."""

from __future__ import annotations

from pathlib import Path


def within(path: Path, root: Path) -> bool:
    """Whether ``path`` lands inside ``root`` (both sides resolved, so a
    symlinked path is judged by where it actually points)."""
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False
