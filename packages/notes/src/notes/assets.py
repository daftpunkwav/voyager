"""Note image attachments: the add_asset capability plus controlled
asset storage.

Responsibilities:
- Reference form: content refers to `attachment://<asset_id>`; the renderer
  resolves it to the controlled route /api/notes/assets/<id>. This decouples
  content from storage location and funnels access through a single entry
  point.
- Content addressing: a file is never overwritten once its asset_id is
  minted (the precondition for immutable caching); replacing an image means
  adding a new asset and referencing it.
- add_asset is the only write entry point (file_path must live under
  workspace/ — browser uploads go through gateway /api/uploads, agents drop
  files there with their own file tools); the routes are read-only.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from platform_capability import Registry, capability
from platform_contracts import ErrorSuffix, ServiceError

from .domain import DOMAIN as _DOMAIN

if TYPE_CHECKING:
    from fastapi import APIRouter

#: Whitelist of extensions allowed as note images (everything else is rejected;
#: no content sniffing).
# SVG is excluded: it can embed scripts and poses a stored-XSS surface when
# inlined same-origin.
ALLOWED_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


class AssetStore:
    """note_assets table: asset_id -> on-disk path; separate namespace (assets.db)."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS note_assets (
        asset_id  TEXT PRIMARY KEY,
        note_id   TEXT NOT NULL DEFAULT '',
        filename  TEXT NOT NULL DEFAULT '',
        ext       TEXT NOT NULL DEFAULT '',
        path      TEXT NOT NULL,
        size      INTEGER NOT NULL DEFAULT 0,
        created_ts REAL NOT NULL
    );
    """

    def __init__(self, db_path: str | Path) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(self._SCHEMA)
        self._lock = threading.Lock()

    def add(self, asset: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO note_assets"
                " (asset_id, note_id, filename, ext, path, size, created_ts)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    asset["asset_id"],
                    asset.get("note_id", ""),
                    asset.get("filename", ""),
                    asset.get("ext", ""),
                    asset["path"],
                    int(asset.get("size", 0)),
                    asset["created_ts"],
                ),
            )
            self._conn.commit()

    def get(self, asset_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT asset_id, note_id, filename, ext, path, size, created_ts"
                " FROM note_assets WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
        if row is None:
            return None
        return dict(
            zip(("asset_id", "note_id", "filename", "ext", "path", "size", "created_ts"), row)
        )

    def remove_of_note(self, note_id: str) -> list[str]:
        """Delete all asset records for a note and return their file paths
        (the caller deletes the files).
        """
        with self._lock:
            paths = [
                r[0]
                for r in self._conn.execute(
                    "SELECT path FROM note_assets WHERE note_id = ?",
                    (note_id,),
                ).fetchall()
            ]
            self._conn.execute("DELETE FROM note_assets WHERE note_id = ?", (note_id,))
            self._conn.commit()
        return paths

    def close(self) -> None:
        self._conn.close()


_store: AssetStore | None = None
_workspace: Path | None = None
_max_file_mb: Callable[[], int] | None = None


def init_store(
    store: AssetStore, workspace: Path, max_file_mb: Callable[[], int] | None = None
) -> None:
    global _store, _workspace, _max_file_mb
    _store = store
    _workspace = workspace
    _max_file_mb = max_file_mb


def require_store() -> AssetStore:
    if _store is None:
        raise RuntimeError(
            "assets not injected: call init_store() at the service entry point first"
        )
    return _store


def purge_of_note(note_id: str) -> list[str]:
    """Delete a note's assets (records plus files); returns removed paths for auditing."""
    store = require_store()
    paths = store.remove_of_note(note_id)
    for p in paths:
        Path(p).unlink(missing_ok=True)
    return paths


def register(registry: Registry) -> None:
    """Register add_asset into the notes registry (called from wiring; avoids a
    circular import with capabilities).

    The registry is a module-level singleton: repeated wire() calls (tests
    assemble multiple times) skip registration and only rebind deps.
    """
    if "add_asset" in registry:
        return

    @capability(
        registry,
        name="add_asset",
        description="Add an image attachment to a note: copy the file into the asset area and return an attachment:// reference."
        " file_path must live under workspace/ (browser uploads go through /api/uploads,"
        " agents drop files there with file tools).",
        cost=1,
    )
    async def add_asset(file_path: str, filename: str = "", note_id: str = "") -> dict:
        store = require_store()
        src = Path(file_path)
        if not src.is_file():
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"File not found: {file_path}")
        ext = src.suffix.lower()
        if ext not in ALLOWED_EXTS:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"Unsupported image format: {ext}",
                hint=f"Only {'/'.join(ALLOWED_EXTS)} are allowed",
            )
        limit_mb = _max_file_mb() if _max_file_mb else 20
        if limit_mb > 0 and src.stat().st_size > limit_mb * 1024 * 1024:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"Image exceeds the size limit of {limit_mb}MB",
                hint="Adjust via the notes.assets.max_mb setting",
            )
        root = _workspace if _workspace else Path("data/workspace")
        root_resolved = Path(root).resolve()
        src_resolved = src.resolve(strict=True)
        if not src_resolved.is_relative_to(root_resolved):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.FORBIDDEN,
                "File must live under workspace/ (uploaded via /api/uploads)",
            )
        asset_id = uuid.uuid4().hex[:12]
        assets_dir = Path(root) / "notes-assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        dest = assets_dir / f"{asset_id}{ext}"
        dest_resolved = dest.resolve()
        if not dest_resolved.is_relative_to(root_resolved):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.FORBIDDEN,
                "Destination path escaped the workspace; check the workspace configuration",
            )
        # Re-resolve right before copying and copy the resolved path, so a
        # symlink swapped in mid-flight cannot escape the jail.
        src_copy = src.resolve(strict=True)
        if src_copy != src_resolved or not src_copy.is_relative_to(root_resolved):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.FORBIDDEN,
                "File must live under workspace/ (uploaded via /api/uploads)",
            )
        if not dest.resolve().is_relative_to(root_resolved):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.FORBIDDEN,
                "Destination path escaped the workspace; check the workspace configuration",
            )
        shutil.copy2(src_copy, dest)
        safe_name = _UNSAFE_FILENAME_RE.sub("_", filename or src.name)[:120]
        store.add(
            {
                "asset_id": asset_id,
                "note_id": note_id,
                "filename": safe_name,
                "ext": ext,
                "path": str(dest),
                "size": src.stat().st_size,
                "created_ts": time.time(),
            }
        )
        return {
            "asset_id": asset_id,
            "url": f"/api/notes/assets/{asset_id}",
            "markdown": f"![{safe_name}](attachment://{asset_id})",
        }


def build_assets_router() -> APIRouter:
    """Read-only asset routes: /assets/{asset_id} (the mounter supplies the
    /api/notes prefix).

    Content addressing makes immutable caching valid; paths come from a
    database lookup by id, which inherently prevents path traversal.
    """
    from fastapi import APIRouter
    from fastapi.responses import FileResponse

    router = APIRouter(prefix="/assets")

    @router.get("/{asset_id}")
    async def get_asset(asset_id: str) -> FileResponse:
        store = require_store()
        asset = store.get(asset_id)
        if asset is None:
            raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"Attachment not found: {asset_id}")
        path = Path(asset["path"])
        if not path.is_file():
            raise ServiceError(
                _DOMAIN, ErrorSuffix.NOT_FOUND, f"Attachment file is missing: {asset['filename']}"
            )
        return FileResponse(
            str(path),
            media_type=_MEDIA_TYPES.get(asset["ext"], "application/octet-stream"),
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    return router
