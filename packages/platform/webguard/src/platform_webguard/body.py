"""Bounded response-body reading: cap how many bytes a fetch may buffer.

A timeout bounds duration, not size — a whitelisted host returning
gigabytes could otherwise exhaust memory before any text-level truncation
runs. The reader stops early and closes the stream; the server may see a
truncated download, which is fine for page-text consumers.
"""

from __future__ import annotations

from typing import Any

#: Absolute read cap shared by the consumers (agent web tools and the
#: sources page importer). Far above any sane page's text needs.
DEFAULT_MAX_BYTES = 2_000_000


async def read_bounded(response: Any, max_bytes: int = DEFAULT_MAX_BYTES) -> bytes:
    """Read a streaming httpx response body up to ``max_bytes``, then stop.

    ``response`` must be an open stream (``client.send(..., stream=True)`` or
    ``client.stream(...)``) whose body has not been read yet; the response is
    closed on exit. Duck-typed on ``aiter_bytes``/``aclose`` so tests can
    pass fakes.
    """
    chunks: list[bytes] = []
    size = 0
    try:
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size >= max_bytes:
                break
    finally:
        await response.aclose()
    return b"".join(chunks)[:max_bytes]


__all__ = ["DEFAULT_MAX_BYTES", "read_bounded"]
