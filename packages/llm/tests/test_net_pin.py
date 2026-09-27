"""Request-time egress pinning (net_pin) and write-path base_url hardening.

The offline-resolver autouse fixture from conftest is overridden here: these
tests inject their own resolvers to prove the private/public/dual-stack
decision logic and that intranet IPs never leak into error messages.
"""

from __future__ import annotations

import pytest
from llm.net_pin import pinned_ip
from platform_contracts import ServiceError
from platform_webguard import ResolutionError


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

    async def test_dns_failure_maps_to_unavailable_not_forbidden(self, monkeypatch) -> None:
        """A transient outage (ResolutionError) is retryable UNAVAILABLE, not
        a FORBIDDEN policy violation that would tell the agent to give up."""
        from llm import net_pin

        async def fake_resolve_public(url: str, *, resolver=None) -> str:
            raise ResolutionError("DNS resolution failed for api.test: no answer")

        monkeypatch.setattr(net_pin, "resolve_public", fake_resolve_public)
        provider = {"base_url": "https://api.test/v1"}
        with pytest.raises(ServiceError) as exc:
            await pinned_ip(provider)
        assert exc.value.body.code.endswith("UNAVAILABLE")
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


class TestLegacyMigrationBackfill:
    """Pre-flag rows get private_endpoint backfilled during the column
    migration: an upgraded local-Ollama provider (the built-in preset is the
    hostname form http://localhost:11434/v1) must keep working."""

    def test_legacy_hostname_private_row_backfilled(self, tmp_path) -> None:
        import sqlite3

        db = tmp_path / "llm.db"
        # Build the pre-migration schema by hand (no private_endpoint column)
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE providers (
                id TEXT PRIMARY KEY, display_name TEXT NOT NULL, preset_id TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL, api_format TEXT NOT NULL, models TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1, custom INTEGER NOT NULL DEFAULT 0,
                created_ts REAL NOT NULL, updated_ts REAL NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO providers (id, display_name, base_url, api_format, created_ts, updated_ts)"
            " VALUES ('p1', 'Ollama (local)', 'http://localhost:11434/v1', 'chat', 1, 1)"
        )
        conn.commit()
        conn.close()

        from llm.store import ProviderStore

        store = ProviderStore(db)
        row = store.get("p1")
        assert row is not None and row["private_endpoint"] == 1

    def test_legacy_public_row_stays_zero(self, tmp_path) -> None:
        import sqlite3

        db = tmp_path / "llm.db"
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE providers (
                id TEXT PRIMARY KEY, display_name TEXT NOT NULL, preset_id TEXT NOT NULL DEFAULT '',
                base_url TEXT NOT NULL, api_format TEXT NOT NULL, models TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1, custom INTEGER NOT NULL DEFAULT 0,
                created_ts REAL NOT NULL, updated_ts REAL NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO providers (id, display_name, base_url, api_format, created_ts, updated_ts)"
            " VALUES ('p2', 'Anthropic', 'https://api.anthropic.com', 'anthropic', 1, 1)"
        )
        conn.commit()
        conn.close()

        from llm.store import ProviderStore

        store = ProviderStore(db)
        row = store.get("p2")
        assert row is not None and row["private_endpoint"] == 0


class TestPrivateEndpointResolutionFailures:
    async def test_private_host_resolution_failure_maps_to_unavailable(self, monkeypatch) -> None:
        _patch_resolver(monkeypatch, {})  # every host fails to resolve
        provider = {"base_url": "http://localhost:11434", "private_endpoint": True}
        with pytest.raises(ServiceError) as exc:
            await pinned_ip(provider)
        assert exc.value.body.code.endswith("UNAVAILABLE")
        assert "localhost" in exc.value.body.message  # host is fine to name, not the IP

    async def test_private_host_resolving_to_nothing_maps_to_unavailable(self, monkeypatch) -> None:
        _patch_resolver(monkeypatch, {"localhost": []})
        provider = {"base_url": "http://localhost:11434", "private_endpoint": True}
        with pytest.raises(ServiceError) as exc:
            await pinned_ip(provider)
        assert exc.value.body.code.endswith("UNAVAILABLE")
