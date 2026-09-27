"""Shared test fixtures for the llm domain."""

from __future__ import annotations

import pytest

#: Fake pinned IP the offline resolver hands back: a public address, so the
#: default provider fixtures (https://api.test/v1) pass request-time pinning
#: without any real DNS traffic.
_PUBLIC_TEST_IP = "93.184.216.34"


@pytest.fixture(autouse=True)
def _offline_pin_resolver(monkeypatch):
    """Resolve-and-pin runs on every request path now: keep the suite offline
    by stubbing the public resolver. Pin-behaviour tests override this by
    patching llm.net_pin again with their own fakes."""
    from llm import net_pin

    async def fake_resolve_public(url: str, *, resolver=None) -> str:
        return _PUBLIC_TEST_IP

    monkeypatch.setattr(net_pin, "resolve_public", fake_resolve_public)
