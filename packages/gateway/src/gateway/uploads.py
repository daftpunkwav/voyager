"""Browser file upload endpoint (the import transport).

Uploading is an HTTP transport action, not a domain capability: the
capability channel stays pure JSON (gen_rest does not carry multipart).
This endpoint only lands files under workspace/imports/ and returns the
server-side path; business validation (type / size limits / path
escapes) is enforced later by domain capabilities (e.g.
sources.add_document, notes.add_asset) inside their guard chains.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile
from starlette.types import Message

from .common import actor_of
from .ratelimit import RateLimiter

log = logging.getLogger("gateway.uploads")

#: Default transport-level cap of 1GB (domains enforce smaller limits);
#: overridden by the gateway.uploads.max_mb setting via create_app.
_MAX_BYTES = 1024 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024  # read in 1MB chunks to bound concurrent memory use
#: Idle seconds between received body chunks before the upload is abandoned:
#: a client that stalls mid-body would otherwise pin a connection and
#: Starlette's spool temp file indefinitely. Generous on purpose — this is a
#: stall detector, not a speed limit; the multipart parse consumes the whole
#: body through the receive boundary below, so this single timeout covers the
#: entire network-transfer phase.
_IDLE_TIMEOUT_S = 30.0

_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def build_upload_router(
    workspace: Path, limiter: RateLimiter, *, max_bytes: int = _MAX_BYTES
) -> APIRouter:
    router = APIRouter()

    @router.post("/api/uploads")
    async def upload(request: Request) -> JSONResponse:
        # Throttled before any byte of the body is read, same as every other
        # gateway route: an upload is the cheapest way to flood the process.
        limiter.check(actor_of(request).id)
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

        def _too_large() -> JSONResponse:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "GATEWAY.PAYLOAD_TOO_LARGE",
                        "message": f"file exceeds the {max_bytes // (1024 * 1024)}MB transport limit",
                    }
                },
            )

        declared = request.headers.get("content-length")
        try:
            if declared is not None and int(declared) > max_bytes:
                return _too_large()
        except ValueError:
            pass

        class _TooLarge(Exception):
            pass

        class _Stalled(Exception):
            pass

        # Enforce the byte cap at the ASGI receive boundary: request.form()
        # spools the whole body to a temp file before returning, so a lying
        # (small) Content-Length or a chunked body would otherwise fill the
        # disk before any of our own checks ran. Counting inside receive
        # stops the spool the moment the cap is crossed; the same boundary
        # carries the idle timeout, so a client that stops sending mid-body
        # cannot hold the connection and its spool temp file forever. The
        # async with below closes Starlette's spool on the success path; an
        # aborted parse never reaches that exit, and the abandoned spool is
        # closed by garbage collection instead.
        bytes_seen = 0
        receive = request._receive

        async def _capped_receive() -> Message:
            nonlocal bytes_seen
            try:
                message = await asyncio.wait_for(receive(), timeout=_IDLE_TIMEOUT_S)
            except TimeoutError:
                raise _Stalled from None
            if message["type"] == "http.request":
                bytes_seen += len(message.get("body", b""))
                if bytes_seen > max_bytes:
                    raise _TooLarge
            return message

        request._receive = _capped_receive
        try:
            async with request.form(max_files=1, max_fields=4) as form:
                file = form.get("file")
                if not isinstance(file, UploadFile):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "code": "GATEWAY.INVALID_INPUT",
                                "message": "missing the file field",
                            }
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

                # Stream in chunks so concurrent uploads never load whole
                # files in memory. The copy must stay inside the with block:
                # exiting it closes the spooled temp file behind UploadFile.
                # (The copy reads the local spool, not the network — the idle
                # timeout above already covered the transfer phase.)
                total = 0
                try:
                    with dest.open("wb") as f:
                        while True:
                            chunk = await file.read(_CHUNK_SIZE)
                            if not chunk:
                                break
                            total += len(chunk)
                            if total > max_bytes:
                                raise _TooLarge
                            f.write(chunk)
                except _TooLarge:
                    dest.unlink(missing_ok=True)
                    return _too_large()
                except Exception as exc:
                    dest.unlink(missing_ok=True)
                    # Exception detail (paths, permission errors) goes to the
                    # server log only; the client gets a generic message
                    log.warning("upload stream failed: %s", exc, exc_info=True)
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": {
                                "code": "GATEWAY.INVALID_INPUT",
                                "message": "failed to read the upload stream",
                            }
                        },
                    )
        except _Stalled:
            # Nothing landed (the destination is created only after a
            # successful parse), so there is no half-written file to clean.
            log.warning("upload stalled: no body data for %ss", _IDLE_TIMEOUT_S)
            return JSONResponse(
                status_code=408,
                content={
                    "error": {
                        "code": "GATEWAY.UPLOAD_TIMEOUT",
                        "message": f"upload stalled: no data received for {_IDLE_TIMEOUT_S:.0f}s",
                    }
                },
            )
        except _TooLarge:
            return _too_large()
        except Exception as exc:
            # Multipart parse failures (malformed bodies) surface as 400;
            # detail goes to the server log only
            log.warning("upload parse failed: %s", exc, exc_info=True)
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "GATEWAY.INVALID_INPUT",
                        "message": "failed to read the upload stream",
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
            # Echo the sanitized name: clients use it as the display name and
            # pass it onward, so it must match the file actually on disk.
            content={"file_path": str(dest), "filename": safe_name, "size": total},
        )

    return router
