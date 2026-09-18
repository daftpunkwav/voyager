"""DNS resolve-and-pin tests: literal handling, intranet rejection, and the
fail-closed resolver-error path (fully offline via injected resolvers).
"""

import pytest
from platform_webguard.dns_pin import literal_ips, resolve_public

_PUBLIC = "93.184.216.34"


class TestResolvePublic:
    async def test_returns_first_validated_ip(self) -> None:
        async def resolver(host: str, port: int) -> list[str]:
            return [_PUBLIC, "1.2.3.4"]

        assert await resolve_public("http://example.com/x", resolver=resolver) == _PUBLIC

    async def test_resolver_failure_fails_closed(self) -> None:
        """A resolver error must raise: returning the raw hostname would send
        an unvalidated string back as the pinned IP and reopen the rebinding
        window on the HTTP client's own resolution."""

        async def resolver(host: str, port: int) -> list[str]:
            raise OSError("name or service not known")

        with pytest.raises(ValueError, match="example.com"):
            await resolve_public("http://example.com/x", resolver=resolver)

    async def test_intranet_answer_rejected(self) -> None:
        async def resolver(host: str, port: int) -> list[str]:
            return ["169.254.169.254"]

        with pytest.raises(ValueError, match="intranet"):
            await resolve_public("http://example.com/x", resolver=resolver)

    async def test_literal_ip_validated_directly(self) -> None:
        # Literal hosts skip the resolver entirely (resolver would raise)
        async def resolver(host: str, port: int) -> list[str]:
            raise AssertionError("resolver must not be called for IP literals")

        assert await resolve_public("http://93.184.216.34/x", resolver=resolver) == "93.184.216.34"
        with pytest.raises(ValueError, match="non-public|intranet"):
            await resolve_public("http://127.0.0.1/x", resolver=resolver)


class TestLiteralIps:
    def test_ip_literal(self) -> None:
        assert literal_ips("93.184.216.34") == ["93.184.216.34"]

    def test_hostname_returns_none(self) -> None:
        assert literal_ips("example.com") is None
