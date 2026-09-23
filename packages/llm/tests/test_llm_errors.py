"""Provider error classification and transient retry tests.

All network egress is mocked (httpx.MockTransport), tests never touch the
network; retry backoff is captured via a client_mod._sleep stand-in so no
real waiting happens.
"""

import httpx
import pytest
from llm import client as client_mod
from llm.capabilities import Deps, init_deps, registry
from llm.capabilities import common as caps
from llm.client import (
    AuthError,
    ContextOverflowError,
    ProviderError,
    RateLimitError,
    TransientError,
)
from llm.store import ProviderStore
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ErrorSuffix, ServiceError
from platform_secrets import SecretStore

_CHAT = {"id": "p1", "api_format": "chat", "base_url": "https://api.test/v1"}
USER_CTX = ActorContext(actor=LOCAL_USER)


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            "model": "m",
        },
    )


@pytest.fixture(autouse=True)
def _fast_retry(monkeypatch):
    """Swap real backoff sleeps for recording: capture the delay sequence,
    no waiting."""
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    monkeypatch.setattr(client_mod, "_sleep", fake_sleep)
    yield delays


@pytest.fixture
def deps(tmp_path):
    store = ProviderStore(tmp_path / "llm.db")
    secrets = SecretStore(tmp_path / "secrets.db", key_material="test")
    init_deps(Deps(store=store, secrets=secrets))
    yield store, secrets
    store.close()
    secrets.close()


def _patch(monkeypatch, handler) -> None:
    real = client_mod.httpx.AsyncClient
    monkeypatch.setattr(
        client_mod.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


class TestClassification:
    async def test_429_becomes_rate_limit_error(self, monkeypatch) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(429, headers={"retry-after": "2"}, text="rate")

        _patch(monkeypatch, handler)
        with pytest.raises(RateLimitError) as exc:
            await client_mod.complete(
                _CHAT, api_key="sk", model="m", messages=[{"role": "user", "content": "hi"}]
            )
        assert exc.value.retriable
        assert exc.value.retry_after == 2.0
        assert calls["n"] == 3  # first try + 2 retries

    async def test_500_transient_then_success(self, monkeypatch) -> None:
        """A 5xx transient error is retried with backoff; success on the
        second try returns the full result."""
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(503, text="overloaded")
            return _ok(request)

        _patch(monkeypatch, handler)
        out = await client_mod.complete(
            _CHAT, api_key="sk", model="m", messages=[{"role": "user", "content": "hi"}]
        )
        assert out.text == "ok"
        assert calls["n"] == 2

    async def test_401_auth_error_no_retry(self, monkeypatch) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(401, text="bad key")

        _patch(monkeypatch, handler)
        with pytest.raises(AuthError):
            await client_mod.complete(
                _CHAT, api_key="sk", model="m", messages=[{"role": "user", "content": "hi"}]
            )
        assert calls["n"] == 1  # retrying auth failures is pointless

    async def test_400_overflow_becomes_context_overflow(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="This model's maximum context length is 8192 tokens")

        _patch(monkeypatch, handler)
        with pytest.raises(ContextOverflowError):
            await client_mod.complete(
                _CHAT, api_key="sk", model="m", messages=[{"role": "user", "content": "hi"}]
            )

    async def test_400_plain_is_not_overflow(self, monkeypatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="invalid params (2013)")

        _patch(monkeypatch, handler)
        with pytest.raises(ProviderError) as exc:
            await client_mod.complete(
                _CHAT, api_key="sk", model="m", messages=[{"role": "user", "content": "hi"}]
            )
        assert not isinstance(exc.value, ContextOverflowError)

    async def test_connect_error_retried_then_raises_transient(self, monkeypatch) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.ConnectError("refused", request=request)

        _patch(monkeypatch, handler)
        with pytest.raises(TransientError) as exc:
            await client_mod.complete(
                _CHAT, api_key="sk", model="m", messages=[{"role": "user", "content": "hi"}]
            )
        assert exc.value.retriable
        assert calls["n"] == 3

    async def test_read_timeout_not_retried(self, monkeypatch) -> None:
        """Read timeout after connection established: the request may have
        been accepted; stop on first failure."""
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.ReadTimeout("slow", request=request)

        _patch(monkeypatch, handler)
        with pytest.raises(TransientError) as exc:
            await client_mod.complete(
                _CHAT, api_key="sk", model="m", messages=[{"role": "user", "content": "hi"}]
            )
        assert not exc.value.retriable
        assert calls["n"] == 1

    async def test_backoff_retry_after_cap(self, monkeypatch, _fast_retry) -> None:
        """Retry-After takes effect but is capped at 5s."""
        monkeypatch.setattr(client_mod, "_RETRY_AFTER_CAP", 5.0)

        async def fail():
            raise RateLimitError("rate", status=429, retriable=True, retry_after=30.0)

        with pytest.raises(RateLimitError):
            await client_mod._send_with_retry(fail)
        assert _fast_retry == [5.0, 5.0]  # max(0.5, min(30, 5)) = 5

    async def test_retry_after_header_parsed(self) -> None:
        resp = httpx.Response(429, headers={"retry-after": "7"})
        assert client_mod._retry_after_seconds(resp) == 7.0
        assert client_mod._retry_after_seconds(httpx.Response(429)) == 0.0
        assert (
            client_mod._retry_after_seconds(
                httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"})
            )
            == 0.0
        )  # HTTP-date format unsupported, treated as no hint


class TestCapabilityMapping:
    async def _setup_provider(self, deps) -> str:
        pid = (
            await execute(
                registry,
                "add_provider",
                USER_CTX,
                {
                    "display_name": "Test Provider",
                    "base_url": "https://api.test/v1",
                    "api_format": "chat",
                    "models": ["m1"],
                },
            )
        )["id"]
        await execute(registry, "set_api_key", USER_CTX, {"provider_id": pid, "api_key": "sk"})
        return pid

    async def test_rate_limited_suffix(self, deps, monkeypatch) -> None:
        pid = await self._setup_provider(deps)
        _patch(monkeypatch, lambda r: httpx.Response(429, text="rate"))
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "complete",
                USER_CTX,
                {"provider_id": pid, "messages": [{"role": "user", "content": "hi"}]},
            )
        assert exc.value.body.code == "LLM.RATE_LIMITED"

    async def test_auth_suffix(self, deps, monkeypatch) -> None:
        pid = await self._setup_provider(deps)
        _patch(monkeypatch, lambda r: httpx.Response(401, text="bad"))
        with pytest.raises(ServiceError) as exc:
            await execute(
                registry,
                "complete",
                USER_CTX,
                {"provider_id": pid, "messages": [{"role": "user", "content": "hi"}]},
            )
        assert exc.value.body.code == "LLM.AUTH_REQUIRED"


class TestServiceErrorFor:
    def test_mapping_table(self) -> None:
        cases = [
            (RateLimitError("x"), ErrorSuffix.RATE_LIMITED),
            (AuthError("x"), ErrorSuffix.AUTH_REQUIRED),
            (ContextOverflowError("x"), ErrorSuffix.INVALID_INPUT),
            (TransientError("x"), ErrorSuffix.UNAVAILABLE),
            (ProviderError("x"), ErrorSuffix.UNAVAILABLE),
        ]
        for exc, suffix in cases:
            assert caps.service_error_for(exc).body.code == f"LLM.{suffix.value}"

    def test_detail_suffix_appended_to_message(self) -> None:
        """request_id / dump_path captured by the client ride into the
        ServiceError message — the user-facing degraded reply names them."""
        exc = ProviderError("HTTP 400: bad", status=400, request_id="req-1", dump_path="/d/x.json")
        body = caps.service_error_for(exc).body
        assert body.message.endswith("(request id req-1, dump /d/x.json)")
        # empty pieces are skipped entirely
        assert caps.service_error_for(ProviderError("x")).body.message == "LLM call failed: x"
        assert caps.service_error_for(ProviderError("x", request_id="r")).body.message.endswith(
            "(request id r)"
        )

    def test_detail_suffix_via_raise_path(self, monkeypatch) -> None:
        """_raise_typed carries the x-request-id response header into the
        raised error's request_id (the _post error path)."""
        import httpx as _httpx
        from llm import client as client_mod

        resp = _httpx.Response(429, text="rate limited", headers={"x-request-id": "rid-9"})
        monkeypatch.setattr(client_mod, "_retry_after_seconds", lambda r: 0.0, raising=False)
        with pytest.raises(RateLimitError) as exc_info:
            client_mod._raise_typed(resp)
        assert exc_info.value.request_id == "rid-9"
        assert "request id rid-9" in exc_info.value.detail_suffix()
