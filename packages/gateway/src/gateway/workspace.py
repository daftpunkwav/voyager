"""Workspace browsing: read-only file tree, file preview, and a machine-wide
directory picker for choosing the workspace root.

Splits read-only file operations into three endpoints:
- /api/workspace/list: entries of one directory INSIDE the workspace (the
  UI file tree; containment is enforced);
- /api/workspace/read: a capped text preview of one workspace file;
- /api/workspace/pick: entries of ANY directory on the machine (the
  directory chooser used to pick a new workspace root). Read-only listing
  of the local filesystem is acceptable for this single-user local
  deployment; the web directory picker makes the same containment trade.

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


def _safe_entries(dir_path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Return a sorted list of directory entries capped at _MAX_ENTRIES plus a
    flag telling the caller whether the directory had more children than the
    cap. Individual unreadable children are skipped silently."""
    entries: list[dict[str, Any]] = []
    try:
        children = sorted(
            dir_path.iterdir(),
            key=lambda p: (p.is_file(), p.name.lower()),
        )
    except (PermissionError, OSError):
        return entries, False
    truncated = len(children) > _MAX_ENTRIES
    for child in children[:_MAX_ENTRIES]:
        try:
            if child.is_dir():
                entries.append({"name": child.name, "type": "directory"})
            else:
                entries.append({"name": child.name, "type": "file", "size": child.stat().st_size})
        except (PermissionError, OSError):
            continue
    return entries, truncated


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


def _denied(message: str) -> dict:
    return {"error": {"code": "WORKSPACE.DENIED", "message": message}}


def _not_found(message: str) -> dict:
    return {"error": {"code": "WORKSPACE.NOT_FOUND", "message": message}}


def _bad_input(message: str) -> dict:
    return {"error": {"code": "GATEWAY.INVALID_INPUT", "message": message}}


def build_workspace_router(workspace: Path, *, home: str | None = None) -> APIRouter:
    router = APIRouter()
    home_path = Path(home or Path.home())

    @router.get("/api/workspace/list")
    def list_dir(path: str = "") -> dict:
        target = _resolve_inside(workspace, path)
        if target is None:
            return _not_found("path escapes workspace")
        try:
            if not target.exists():
                return _not_found("path not found")
            if not target.is_dir():
                return _bad_input("not a directory")
        except (PermissionError, OSError):
            return _denied("cannot read the path")
        entries, truncated = _safe_entries(target)
        return {
            "path": path,
            "entries": entries,
            "truncated": truncated,
        }

    @router.get("/api/workspace/read")
    def read_file(path: str = "", limit: int = _PREVIEW_MAX_LINES) -> dict:
        target = _resolve_inside(workspace, path)
        if target is None:
            return _not_found("path escapes workspace")
        limit = max(1, min(int(limit), _PREVIEW_MAX_LINES))
        try:
            if not target.is_file():
                return _not_found("file not found")
            # Read only one byte more than the preview cap so huge files never
            # land fully in memory; the +1 tells us whether the cap was hit.
            with target.open("rb") as fh:
                data = fh.read(_PREVIEW_MAX_BYTES + 1)
            if not _looks_textual(data):
                return {
                    "error": {
                        "code": "WORKSPACE.NOT_TEXT",
                        "message": "file does not look like text",
                    }
                }
            # The preview cap is inclusive, so trim the trailing +1 byte if
            # it was read only to detect overflow.
            capped = data[:_PREVIEW_MAX_BYTES]
            lines = capped.decode("utf-8", errors="replace").splitlines()[:limit]
            total_bytes = target.stat().st_size
            truncated = total_bytes > _PREVIEW_MAX_BYTES or len(lines) >= limit
        except OSError:
            return _denied("cannot read the file")
        return {
            "path": path,
            "lines": lines,
            "total_bytes": total_bytes,
            "truncated": truncated,
        }

    @router.get("/api/workspace/pick")
    def pick(path: str = "") -> dict:
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
                return _not_found("path not found")
            if not resolved.is_dir():
                return _bad_input("not a directory")
        except (PermissionError, OSError):
            return _denied("cannot read the path")
        parent = str(resolved.parent) if resolved.parent != resolved else None
        entries, truncated = _safe_entries(resolved)
        return {
            "path": str(resolved),
            "parent": parent,
            "home": str(home_path),
            "entries": entries,
            "truncated": truncated,
        }

    return router
