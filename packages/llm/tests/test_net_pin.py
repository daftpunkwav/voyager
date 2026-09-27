"""Request-time egress pinning (net_pin) and write-path base_url hardening.

The offline-resolver autouse fixture from conftest is overridden here: these
tests inject their own resolvers to prove the private/public/dual-stack
decision logic and that intranet IPs never leak into error messages.
"""

from __future__ import annotations

import pytest
from llm.net_pin import pinned_ip
from platform_contracts import ServiceError


def _patch_resolver(monkeypatch, answers: dict[str, list[str]]):
    """Replace net_pin's resolver with an offline fake: host -> IPs."""
    from llm import net_pin

    async def fake_resolver(host: str, port: int) -> list[str]:
        if host in answers:
            return answers[host]
        raise OSError(f"no answer for {host}")

    monkeypatch.setattr(net_pin, "default_resolver", fake_resolver)


class TestPinnedIp:
    async def test_private_endpoint_resolves_without_rejection(self, monkeypatch) -> None:
        """A USER-authorized private endpoint (local Ollama) resolves and is
        never rejected — the documented deployment shape must keep working."""
        _patch_resolver(monkeypatch, {"localhost": ["127.0.0.1"]})
        provider = {"base_url": "http://localhost:11434", "private_endpoint": True}
        ip = await pinned_ip(provider)
        assert ip == "127.0.0.1"

    async def test_public_host_resolving_loopback_is_refused(self, monkeypatch) -> None:
        """A public provider whose DNS drifted to loopback is refused before
        any HTTP request exists, and the intranet IP stays out of the error."""
        from llm import net_pin

        async def fake_resolve_public(url: str, *, resolver=None) -> str:
            raise ValueError("api.test resolves to an intranet address 127.0.0.1")

        monkeypatch.setattr(net_pin, "resolve_public", fake_resolve_public)
        provider = {"base_url": "https://api.test/v1", "private_endpoint": False}
        with pytest.raises(ServiceError) as exc:
            await pinned_ip(provider)
        assert exc.value.body.code.endswith("FORBIDDEN")
        assert "127.0.0.1" not in exc.value.body.message
        assert "127.0.0.1" not in (exc.value.body.hint or "")

    async def test_dns_failure_maps_to_service_error(self, monkeypatch) -> None:
        from llm import net_pin

        async def fake_resolve_public(url: str, *, resolver=None) -> str:
            raise ValueError("DNS resolution failed for api.test: no answer")

        monkeypatch.setattr(net_pin, "resolve_public", fake_resolve_public)
        provider = {"base_url": "https://api.test/v1"}
        with pytest.raises(ServiceError) as exc:
            await pinned_ip(provider)
        # Refused either way; the raw DNS detail stays in the log
        assert exc.value.body.code.endswith("FORBIDDEN")
        assert "no answer" not in exc.value.body.message


class TestPrivateEndpointFlag:
    def test_user_private_target_is_flagged(self) -> None:
        from llm.capabilities.common import private_endpoint_flag
        from platform_contracts import ActorKind, ActorRef

        user = ActorRef(kind=ActorKind.USER, id="local")
        assert private_endpoint_flag("http://127.0.0.1:11434", user)

    def test_user_public_target_is_not_flagged(self) -> None:
        from llm.capabilities.common import private_endpoint_flag
        from platform_contracts import ActorKind, ActorRef

        user = ActorRef(kind=ActorKind.USER, id="local")
        assert not private_endpoint_flag("https://api.anthropic.com", user)


class TestHttpsEnforcement:
    def test_public_http_rejected_at_write_path(self) -> None:
        from llm.capabilities.common import validate_base_url
        from platform_contracts import ActorKind, ActorRef, ServiceError

        user = ActorRef(kind=ActorKind.USER, id="local")
        with pytest.raises(ServiceError) as exc:
            validate_base_url("http://api.anthropic.com", user)
        assert exc.value.body.code.endswith("INVALID_INPUT")
        assert "https" in exc.value.body.message

    def test_private_http_still_allowed(self) -> None:
        from llm.capabilities.common import validate_base_url
        from platform_contracts import ActorKind, ActorRef

        user = ActorRef(kind=ActorKind.USER, id="local")
        out = validate_base_url("http://127.0.0.1:11434", user)
        assert out == "http://127.0.0.1:11434"
