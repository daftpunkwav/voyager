"""Read-only download routes for original document files (users see the
original layout; agents do not need them -- they read section text).

Paths are resolved from the DB by doc_id and confined to the stored
location, which inherently blocks path traversal; media types are mapped
from the extension so browsers inline-preview (PDF opens directly).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse
from platform_contracts import ErrorSuffix, ServiceError

from .modules.doc.store import DocStore

_DOMAIN = "sources"

_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".epub": "application/epub+zip",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
}


def build_files_router(store: DocStore) -> APIRouter:
    """/files/doc/{doc_id} (the mount supplies the /api/sources + /files prefix)."""
    router = APIRouter(prefix="/files")

    @router.get("/doc/{doc_id}")
    async def get_doc_file(doc_id: str) -> FileResponse:
        doc = store.get(doc_id)
        if doc is None or not doc["local_path"]:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.NOT_FOUND, f"Document not found or has no local file: {doc_id}"
            )
        path = Path(doc["local_path"])
        if not path.is_file():
            raise ServiceError(
                _DOMAIN, ErrorSuffix.NOT_FOUND, f"Local file is missing: {doc['filename']}"
            )
        return FileResponse(
            str(path),
            media_type=_MEDIA_TYPES.get(doc["ext"], "application/octet-stream"),
            filename=doc["filename"] or path.name,
            content_disposition_type="inline",
        )

    return router
