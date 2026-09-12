"""Shared helpers: node ids, qualified names, complexity heuristics,
git branch, and language detection.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

from .constants import DOC_EXT


def _nid(project: str, qn: str) -> str:
    h = hashlib.sha1(f"{project}:{qn}".encode()).hexdigest()[:16]
    return f"n_{h}"


def _module_qn(project: str, rel: str) -> str:
    """Aligned with the native engine's ModuleQN: project.path.to.file (keeps __init__)."""
    norm = rel.replace("\\", "/").removesuffix("/")
    parts = [project] + [p for p in norm.split("/") if p]
    return ".".join(parts)


def _folder_qn(project: str, rel_dir: str) -> str:
    if not rel_dir or rel_dir in (".", "/"):
        return project
    return ".".join([project] + [p for p in rel_dir.replace("\\", "/").split("/") if p])


def _file_qn(project: str, rel: str) -> str:
    return _module_qn(project, rel) + ".__file__"


def _complexity_attrs(source: str) -> dict:
    loops = len(re.findall(r"\b(for|while|foreach)\b", source))
    branches = len(re.findall(r"\b(if|elif|else|switch|case|catch)\b", source))
    recursion_hint = 1 if "self." in source or re.search(r"\breturn\s+\w+\(", source) else 0
    alloc_in_loop = 1 if loops and re.search(r"(new |malloc|alloc|\[\]|list\()", source) else 0
    return {
        "cyclomatic_complexity": max(1, branches + loops),
        "cognitive_complexity": max(1, branches + loops * 2),
        "loop_depth": min(5, loops),
        "transitive_loop_depth": min(5, loops),
        "linear_scan_in_loop": 1 if loops else 0,
        "alloc_in_loop": alloc_in_loop,
        "unguarded_recursion": recursion_hint,
    }


def _read_git_branch(root: Path) -> str:
    head = root / ".git" / "HEAD"
    try:
        text = head.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return "HEAD"
    if text.startswith("ref:"):
        return text.split("/")[-1] or "HEAD"
    return text[:12] or "HEAD"


def _lang_of(ext: str, name: str) -> str:
    low = name.lower()
    if ext in DOC_EXT:
        return "markdown"
    if ext in {".py", ".pyi"}:
        return "python"
    if ext in {".ts", ".tsx"}:
        return "typescript"
    if ext in {".js", ".jsx", ".mjs", ".cjs"}:
        return "javascript"
    if low.startswith("dockerfile"):
        return "dockerfile"
    return ext.lstrip(".") or "text"


def _is_test_path(rel: str) -> bool:
    low = rel.lower().replace("\\", "/")
    return (
        "/test/" in f"/{low}"
        or "/tests/" in f"/{low}"
        or low.endswith("_test.py")
        or low.endswith(".test.ts")
        or low.endswith(".test.tsx")
        or low.endswith(".spec.ts")
        or low.endswith("_test.go")
    )


def _decorator_str(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        if isinstance(node, ast.Call):
            return _decorator_str(node.func)
        return "decorator"


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None
