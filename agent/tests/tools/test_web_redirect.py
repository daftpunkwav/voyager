"""Per-hop redirect validation for web_fetch: a whitelisted-domain 302 into an
internal address must be refused.

SSRF regression protection: every redirect hop re-passes policy instead of the whole
chain being followed automatically. MockTransport throughout; the tests never touch the
network.
"""

from typing import Any

import agent.tools.net.web_fetch as web_mod
import httpx
from agent.policy import NetworkPolicy, PolicyEngine
from agent.policy.network import host_is_nonglobal


def _client_factory(handler):
    orig = httpx.AsyncClient

    def factory(**kw):
        kw.pop("follow_redirects", None)
        return orig(transport=httpx.MockTransport(handler), follow_redirects=False, **kw)

    return factory


def _fetch(monkeypatch, handler) -> Any:
    monkeypatch.setattr(web_mod.httpx, "AsyncClient", _client_factory(handler))

    async def _resolve(url: str) -> str:
        # Hermetic DNS guard stub: public hosts resolve to a fixed IP (the
        # request is pinned onto it); literal intranet hosts still refuse, so
        # the redirect-to-internal test keeps its rejection semantics offline.
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        if host_is_nonglobal(host):
            raise ValueError(f"{host} resolves to a non-public address")
        return "93.184.216.34"

    monkeypatch.setattr(web_mod, "resolve_public", _resolve)
    policy = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=("github.com",)))
    return web_mod.web_fetch_tool(policy).handler


async def test_redirect_to_internal_is_refused(monkeypatch) -> None:
    """A whitelisted-domain 302 -> link-local address: each hop is revalidated and the internal hop never sends a request."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data"})

    fetch = _fetch(monkeypatch, handler)
    out = await fetch("http://github.com/redirect")

    assert len(calls) == 1  # only the first hop was requested
    # The internal hop is refused before any request (the literal-host
    # network rule fires first: "loopback or private addresses rejected")
    assert "[已拒绝]" in out and "loopback or private" in out


async def test_redirect_within_whitelist_follows(monkeypatch) -> None:
    """Redirects within the whitelist follow normally to the final content."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, text="done")

    fetch = _fetch(monkeypatch, handler)
    out = await fetch("https://github.com/start")
    assert "HTTP 200" in out and "done" in out
