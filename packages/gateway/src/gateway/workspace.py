"""Workspace browsing: read-only file tree, file preview, and a machine-wide
directory picker for choosing the workspace root.

Localized from DSH's `workspaceFiles.list/read` + `directoryPicker` splits:
- /api/workspace/list: entries of one directory INSIDE the workspace (the
  UI file tree; containment is enforced);
- /api/workspace/read: a capped text preview of one workspace file;
- /api/workspace/pick: entries of ANY directory on the machine (the
  directory chooser used to pick a new workspace root). Read-only listing
  of the local filesystem is acceptable for this single-user local
  deployment (DSH makes the same trade for its web directory picker).

All endpoints are read-only; selecting a workspace goes through the
existing settings.set_setting capability (user-only key).
"""

from __future__ import annotations

import os
import string
from pathlib import Path, PureWindowsPath
from typing import Any

from fastapi import APIRouter

_PREVIEW_MAX_BYTES = 256 * 1024
_PREVIEW_MAX_LINES = 400
_MAX_ENTRIES = 2000


def _safe_entries(dir_path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    try:
        children = sorted(
            dir_path.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower()),
        )
    except (PermissionError, OSError):
        return entries
    for child in children[:_MAX_ENTRIES]:
        try:
            if child.is_dir():
                entries.append({"name": child.name, "type": "directory"})
            else:
                entries.append({"name": child.name, "type": "file", "size": child.stat().st_size})
        except (PermissionError, OSError):
            continue
    return entries


def _resolve_inside(workspace: Path, rel: str) -> Path | None:
    """Resolve a workspace-relative path, enforcing containment across drive
    case/mixed separators (normcase comparison over resolved absolutes)."""
    root = workspace.resolve()
    rel_clean = (rel or "").strip().replace("\\", "/").strip("/")
    if rel_clean in ("", "."):
        return root
    candidate = (root / rel_clean).resolve()
    if os.path.normcase(str(candidate)).startswith(os.path.normcase(str(root) + os.sep)) or (
        candidate == root
    ):
        return candidate
    return None


def _looks_textual(data: bytes) -> bool:
    return b"\x00" not in data[:4096]


def build_workspace_router(workspace: Path, *, home: str | None = None) -> APIRouter:
    router = APIRouter()
    home_path = Path(home or Path.home())

    @router.get("/api/workspace/list")
    async def list_dir(path: str = "") -> dict:
        target = _resolve_inside(workspace, path)
        if target is None or not target.exists():
            return {"error": {"code": "WORKSPACE.NOT_FOUND", "message": "path not found"}}
        if not target.is_dir():
            return {"error": {"code": "GATEWAY.INVALID_INPUT", "message": "not a directory"}}
        return {
            "path": path,
            "entries": _safe_entries(target),
            "truncated": False,
        }

    @router.get("/api/workspace/read")
    async def read_file(path: str = "", limit: int = _PREVIEW_MAX_LINES) -> dict:
        target = _resolve_inside(workspace, path)
        if target is None or not target.is_file():
            return {"error": {"code": "WORKSPACE.NOT_FOUND", "message": "file not found"}}
        limit = max(1, min(int(limit), _PREVIEW_MAX_LINES))
        data = target.read_bytes()[:_PREVIEW_MAX_BYTES]
        if not _looks_textual(data):
            return {
                "error": {
                    "code": "WORKSPACE.NOT_TEXT",
                    "message": "file does not look like text",
                }
            }
        lines = data.decode("utf-8", errors="replace").splitlines()[:limit]
        return {
            "path": path,
            "lines": lines,
            "total_bytes": target.stat().st_size,
            "truncated": target.stat().st_size > _PREVIEW_MAX_BYTES or len(lines) >= limit,
        }

    @router.get("/api/workspace/pick")
    async def pick(path: str = "") -> dict:
        """Directory chooser: list any directory on the machine. Empty path on
        Windows lists the drives."""
        if not path.strip():
            drives = [
                {"name": f"{letter}:\\", "type": "directory"}
                for letter in string.ascii_uppercase
                if Path(f"{letter}:\\").exists()
            ]
            return {
                "path": "",
                "parent": None,
                "home": str(home_path),
                "entries": drives,
                "truncated": False,
            }
        target = PureWindowsPath(path)
        resolved = Path(target.anchor + "/".join(target.parts[1:])) if target.drive else Path(path)
        try:
            resolved = resolved.resolve()
            if not resolved.exists():
                return {"error": {"code": "WORKSPACE.NOT_FOUND", "message": "path not found"}}
        except (PermissionError, OSError):
            return {"error": {"code": "WORKSPACE.DENIED", "message": "cannot read the path"}}
        parent = str(resolved.parent) if resolved.parent != resolved else None
        return {
            "path": str(resolved),
            "parent": parent,
            "home": str(home_path),
            "entries": _safe_entries(resolved),
            "truncated": False,
        }

    return router
