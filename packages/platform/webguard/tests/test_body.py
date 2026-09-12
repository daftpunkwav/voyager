"""read_bounded: the body reader stops at the byte cap and closes the
stream — a whitelisted host returning gigabytes cannot exhaust memory."""

from __future__ import annotations

from platform_webguard.body import DEFAULT_MAX_BYTES, read_bounded


class _FakeStreamResponse:
    def __init__(self, chunk: bytes, repeats: int) -> None:
        self._chunk = chunk
        self._repeats = repeats
        self.closed = False
        self.iterations = 0

    async def aiter_bytes(self):
        for _ in range(self._repeats):
            self.iterations += 1
            yield self._chunk

    async def aclose(self) -> None:
        self.closed = True


async def test_stops_at_cap_and_closes() -> None:
    chunk = b"x" * 100_000
    resp = _FakeStreamResponse(chunk, repeats=100)  # 10 MB offered
    data = await read_bounded(resp, max_bytes=250_000)
    assert len(data) == 250_000
    assert resp.closed is True
    assert resp.iterations == 3  # 300k buffered >= cap -> stop before the rest


async def test_short_body_passes_through_completely() -> None:
    resp = _FakeStreamResponse(b"hello", repeats=2)
    data = await read_bounded(resp, max_bytes=DEFAULT_MAX_BYTES)
    assert data == b"hellohello"
    assert resp.closed is True
