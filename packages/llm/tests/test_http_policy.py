"""HttpPolicy override semantics: per-call transport knobs (request timeout /
retries / backoff) resolved against the module constants.

Timeout shapes are asserted on the derived httpx.Timeout values; retry
behavior is asserted on the attempt/delay sequence with a recording sleep,
no network and no real waiting.
"""

import httpx
import pytest
from llm import client as client_mod
from llm.client import HttpPolicy, ProviderError, _complete_timeout, _stream_timeout


@pytest.fixture(autouse=True)
def _recording_sleep(monkeypatch):
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(client_mod, "_sleep", fake_sleep)
    return delays


class TestTimeouts:
    def test_none_policy_keeps_module_defaults(self) -> None:
        """A bare caller (policy=None or all-None fields) is byte-identical
        to the pre-policy defaults."""
        assert _stream_timeout(None).read == 60.0
        assert _stream_timeout(HttpPolicy()).read == 60.0
        assert _complete_timeout(4096, None).read == _complete_timeout(4096).read

    def test_stream_read_follows_request_timeout(self) -> None:
        """Streaming bounds only the inter-chunk gap: the read cap is the
        configured request timeout verbatim; the other phases stay put."""
        t = _stream_timeout(HttpPolicy(request_timeout_s=120.0))
        assert (t.read, t.connect, t.write, t.pool) == (120.0, 10.0, 10.0, 10.0)

    def test_complete_read_is_the_generation_cap(self) -> None:
        """Non-streaming read covers the whole generation: max(derive from
        max_tokens, request timeout) — the request timeout raises the floor
        but never shortens the derived cap."""
        assert _complete_timeout(4096, HttpPolicy(request_timeout_s=120.0)).read == 480.0
        assert _complete_timeout(320, HttpPolicy(request_timeout_s=120.0)).read == 120.0


class TestRetry:
    async def test_attempts_and_backoff_follow_policy(self, _recording_sleep) -> None:
        calls = {"n": 0}

        async def attempt() -> httpx.Response:
            calls["n"] += 1
            if calls["n"] < 4:
                raise ProviderError("transient", retriable=True)
            return httpx.Response(200)

        resp = await client_mod._send_with_retry(
            attempt, HttpPolicy(retry_attempts=3, retry_backoff_s=0.1)
        )
        assert resp.status_code == 200
        assert calls["n"] == 4  # 1 initial + 3 retries
        assert _recording_sleep == [0.1, 0.2, 0.4]  # exponential backoff

    async def test_zero_attempts_fails_fast(self) -> None:
        calls = {"n": 0}

        async def attempt() -> httpx.Response:
            calls["n"] += 1
            raise ProviderError("transient", retriable=True)

        with pytest.raises(ProviderError):
            await client_mod._send_with_retry(attempt, HttpPolicy(retry_attempts=0))
        assert calls["n"] == 1

    async def test_negative_attempts_clamped_to_zero(self) -> None:
        """A dirty negative value must degrade to fail-fast, never empty the
        attempt loop (which would return None instead of a Response)."""
        calls = {"n": 0}

        async def attempt() -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(200)

        resp = await client_mod._send_with_retry(attempt, HttpPolicy(retry_attempts=-2))
        assert resp.status_code == 200
        assert calls["n"] == 1

    async def test_non_retriable_ignores_policy(self) -> None:
        calls = {"n": 0}

        async def attempt() -> httpx.Response:
            calls["n"] += 1
            raise ProviderError("established", retriable=False)

        with pytest.raises(ProviderError):
            await client_mod._send_with_retry(attempt, HttpPolicy(retry_attempts=6))
        assert calls["n"] == 1
