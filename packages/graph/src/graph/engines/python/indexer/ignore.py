""".engineignore (gitignore-style) parsing, matching, and
repository file traversal.

Safety-core directories (constants.SAFETY_CORE_DIRS) can never be included by
any rule, aligned with the C engine's discover.c is_safety_core_dir.
"""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterable
from pathlib import Path

from .constants import ALL_EXT, SAFETY_CORE_DIRS, SKIP_DIRS


def iter_source_files(root: Path, max_files: int) -> Iterable[Path]:
    ignore_rules = _load_engineignore(root)
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        rel_root = Path(dirpath)
        dirnames[:] = [
            d
            for d in dirnames
            if d not in SKIP_DIRS
            and not (
                d.startswith(".")
                and d not in SAFETY_CORE_DIRS
                and not _negated_by(ignore_rules, root, rel_root / d, is_dir=True)
            )
            and not _ignored_by(ignore_rules, root, rel_root / d, is_dir=True)
        ]
        for name in filenames:
            rel_path = rel_root / name
            if _ignored_by(ignore_rules, root, rel_path, is_dir=False):
                continue
            ext = Path(name).suffix.lower()
            # .env / Dockerfile are collected despite having no suffix
            low = name.lower()
            if (
                ext not in ALL_EXT
                and low not in {".env", "dockerfile", "makefile"}
                and not low.startswith(".env.")
                and not low.startswith("dockerfile")
            ):
                continue
            yield rel_path
            count += 1
            if max_files > 0 and count >= max_files:
                return


def _load_engineignore(root: Path) -> list[tuple[str, bool]]:
    """Parse the repository-root .engineignore: returns (pattern, negated).

    Only the single repository-root file is supported (as in the C engine);
    `#` comments, `!` negation, and trailing whitespace are handled.
    """
    rules: list[tuple[str, bool]] = []
    ignore_file = root / ".engineignore"
    if not ignore_file.is_file():
        return rules
    try:
        lines = ignore_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rules
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            rules.append((line[1:].lstrip("/"), True))
        else:
            rules.append((line.lstrip("/"), False))
    return rules


def _rel_posix(repo_root: Path, path: Path) -> str:
    """Convert a path to a posix path relative to the repo root (the matching basis for .engineignore patterns)."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _ignored_by(
    rules: list[tuple[str, bool]], repo_root: Path, path: Path, *, is_dir: bool
) -> bool:
    """Whether the path is ignored by .engineignore. The last matching rule wins (gitignore semantics).

    Safety-core directories must never be un-ignored by negation rules.
    """
    if is_dir and path.name in SAFETY_CORE_DIRS:
        return True
    rel = _rel_posix(repo_root, path)
    verdict = False
    for pattern, negated in rules:
        if _pattern_match(pattern, rel, is_dir):
            verdict = not negated
    return verdict


def _negated_by(
    rules: list[tuple[str, bool]], repo_root: Path, path: Path, *, is_dir: bool
) -> bool:
    """Whether the path is un-ignored by a negation rule (used to admit hidden directories)."""
    if path.name in SAFETY_CORE_DIRS:
        return False
    rel = _rel_posix(repo_root, path)
    verdict = False
    for pattern, negated in rules:
        if negated and _pattern_match(pattern, rel, is_dir):
            verdict = True
    return verdict


def _pattern_match(pattern: str, rel: str, is_dir: bool) -> bool:
    """gitignore-style matching (rel is a posix path relative to the repo root).

    - Directory-scoped patterns end with `/` (e.g. `build/`): match the directory
      and everything under it;
    - Patterns without `/`: match the basename at any depth (e.g. `*.log`);
    - Patterns containing `/`: anchored to the repo-root-relative path.
    """
    dir_only = pattern.endswith("/")
    pat = pattern.rstrip("/")
    if "/" not in pat:
        return fnmatch.fnmatch(Path(rel).name, pat)
    # Contains `/`: anchored to the repo root
    if dir_only:
        return rel == pat or rel.startswith(pat + "/")
    return fnmatch.fnmatch(rel, pat)
