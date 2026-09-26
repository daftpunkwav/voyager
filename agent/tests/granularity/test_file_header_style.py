"""Pin the file-header style for production python modules.

Every production .py file must open with a plain module docstring: a one-line
summary followed by explanation as needed. Legacy magic tags (`@file`,
`@description`) are banned — the docstring speaks for itself, mirroring the
style adopted repo-wide (2026-09-10).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_PY_DOMAINS = ("agent", "packages")
_BANNED_TAGS = ("@file", "@description")


def _iter_source_files() -> list[Path]:
    files: list[Path] = []
    for domain in _PY_DOMAINS:
        for path in (ROOT / domain).rglob("*.py"):
            if "tests" in path.parts or "__pycache__" in path.parts or ".venv" in path.parts:
                continue
            files.append(path)
    return files


def _scan() -> list[str]:
    hits: list[str] = []
    for path in _iter_source_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError, OSError):
            continue
        if not (
            tree.body
            and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)
        ):
            hits.append(f"{path}: missing module docstring")
            continue
        doc = tree.body[0].value.value
        for tag in _BANNED_TAGS:
            if tag in doc:
                hits.append(f"{path}: legacy header tag {tag} in module docstring")
    return hits


def test_plain_docstring_headers() -> None:
    hits = _scan()
    assert not hits, "\n".join(hits[:20])
