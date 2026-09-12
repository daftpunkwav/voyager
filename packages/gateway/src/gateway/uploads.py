"""Browser file upload endpoint (the import transport).

Uploading is an HTTP transport action, not a domain capability: the
capability channel stays pure JSON (gen_rest does not carry multipart).
This endpoint only lands files under workspace/imports/ and returns the
server-side path; business validation (type / size limits / path
escapes) is enforced later by domain capabilities (e.g.
sources.add_document, notes.add_asset) inside their guard chains.
"""

from __future__ import annotations

import re
from datetime import UTC
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

#: Hard cap of 1GB (transport-level limit; domains enforce smaller limits)
_MAX_BYTES = 1024 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024  # read in 1MB chunks to bound concurrent memory use

_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def build_upload_router(workspace: Path) -> APIRouter:
    router = APIRouter()

    @router.post("/api/uploads")
    async def upload(request: Request) -> JSONResponse:
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" not in content_type:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "GATEWAY.INVALID_INPUT",
                        "message": "must be a multipart/form-data upload",
                    }
                },
            )
        form = await request.form()
        file = form.get("file")
        if not isinstance(file, UploadFile):
            return JSONResponse(
                status_code=400,
                content={
                    "error": {"code": "GATEWAY.INVALID_INPUT", "message": "missing the file field"}
                },
            )

        import uuid
        from datetime import datetime

        safe_name = _UNSAFE_FILENAME_RE.sub("_", file.filename or "upload")
        safe_name = safe_name.replace("..", "_").strip(" .")[:120] or "upload"
        month_dir = datetime.now(UTC).strftime("%Y%m")
        dest_dir = Path(workspace) / "imports" / month_dir
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{uuid.uuid4().hex[:12]}__{safe_name}"

        class _TooLarge(Exception):
            pass

        # Stream in chunks so concurrent uploads never load whole files in memory
        total = 0
        try:
            with dest.open("wb") as f:
                while True:
                    chunk = await file.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > _MAX_BYTES:
                        raise _TooLarge
                    f.write(chunk)
        except _TooLarge:
            dest.unlink(missing_ok=True)
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "GATEWAY.PAYLOAD_TOO_LARGE",
                        "message": "file exceeds the 1GB transport limit",
                    }
                },
            )
        except Exception as exc:  # noqa: BLE001
            dest.unlink(missing_ok=True)
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "GATEWAY.INVALID_INPUT",
                        "message": f"failed to read the upload stream: {exc}",
                    }
                },
            )
        if total == 0:
            dest.unlink(missing_ok=True)
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "GATEWAY.INVALID_INPUT", "message": "empty file"}},
            )
        return JSONResponse(
            status_code=201,
            content={"file_path": str(dest), "filename": file.filename or safe_name, "size": total},
        )

    return router
