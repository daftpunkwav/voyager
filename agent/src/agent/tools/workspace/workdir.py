"""The agent's default working directory: self-managed category layout.

Mechanism shared by assembly (build_agent) and tests; not a tool.
"""

from __future__ import annotations

from pathlib import Path

#: Self-managed categories of the agent's default working directory
DEFAULT_CATEGORIES = ("repo", "books", "news", "exports", "imports", "sandbox")


def ensure_workdir(root: str | Path) -> Path:
    """Ensure the agent's default working directory and its category subdirectories exist."""
    root = Path(root)
    for category in DEFAULT_CATEGORIES:
        (root / category).mkdir(parents=True, exist_ok=True)
    return root


__all__ = ["DEFAULT_CATEGORIES", "ensure_workdir"]
