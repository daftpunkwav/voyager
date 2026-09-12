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


def _client_factory(handler):
    orig = httpx.AsyncClient

    def factory(**kw):
        kw.pop("follow_redirects", None)
        return orig(transport=httpx.MockTransport(handler), follow_redirects=False, **kw)

    return factory


def _fetch(monkeypatch, handler) -> Any:
    monkeypatch.setattr(web_mod.httpx, "AsyncClient", _client_factory(handler))
    policy = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=("github.com",)))
    return web_mod.web_fetch_tool(policy).handler


async def test_redirect_to_internal_is_refused(monkeypatch) -> None:
    """A whitelisted-domain 302 -> link-local address: each hop is revalidated and the internal hop never sends a request."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "github.com":
            return httpx.Response(
                302, headers={"location": "http://169.254.169.254/latest/meta-data"}
            )
        raise AssertionError(f"内网地址被实际请求: {request.url}")

    fetch = _fetch(monkeypatch, handler)
    out = await fetch("http://github.com/redirect")

    assert len(calls) == 1  # only the first hop was requested
    # The internal hop is refused by the non-global-literal rule (reason mentions loopback or internal
    # address), while the first hop went through the whitelist; the exact rule is not pinned — either refusing means the block worked
    assert "[已拒绝]" in out and ("allowlist" in out or "loopback" in out or "private" in out)


async def test_redirect_within_whitelist_follows(monkeypatch) -> None:
    """Redirects within the whitelist follow normally to the final content."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/start":
            return httpx.Response(302, headers={"location": "/final"})
        return httpx.Response(200, text="done")

    fetch = _fetch(monkeypatch, handler)
    out = await fetch("https://github.com/start")
    assert "HTTP 200" in out and "done" in out
