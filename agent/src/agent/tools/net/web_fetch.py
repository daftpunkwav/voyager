"""web_fetch tool: fetch a page through the network permission layer.

Redirect safety: the chain is not followed automatically; each hop is
re-checked against the policy whitelist and the shared DNS guard
(platform_webguard — one implementation with the sources domain). The body
is read under a byte cap: a timeout bounds duration, not size, and the
model-controlled max_chars must not be able to lift the memory bound.
"""

from __future__ import annotations

import httpx
from platform_webguard.body import read_bounded
from platform_webguard.dns_pin import resolve_public
from platform_webguard.redirects import MAX_REDIRECTS, redirect_target

from agent.context.provenance import wrap_untrusted
from agent.policy import Action, PolicyEngine
from agent.tools.core.base import AgentTool

_MAX_BODY_BYTES = 2_000_000  # absolute read cap, independent of max_chars
_MAX_CHARS = 12_000


def web_fetch_tool(policy: PolicyEngine | None = None) -> AgentTool:
    async def web_fetch(url: str, max_chars: int = _MAX_CHARS) -> str:
        status = 0
        text = ""
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            for _ in range(MAX_REDIRECTS):
                if policy is not None:
                    decision = policy.decide(Action(dimension="network", target=url))
                    if not decision.allow:
                        return f"[已拒绝] {decision.reason}"
                try:
                    await resolve_public(url)
                except ValueError as exc:
                    return f"[已拒绝] {exc}"
                async with client.stream("GET", url) as resp:
                    status = resp.status_code
                    nxt = redirect_target(url, resp)
                    if nxt is not None:
                        url = nxt  # every hop is re-checked: policy + DNS, above
                        continue
                    raw = await read_bounded(resp, _MAX_BODY_BYTES)
                    charset = resp.charset_encoding or "utf-8"
                text = raw.decode(charset, errors="replace")
                break
        # Truncate the raw body first, then fence: the closing marker must
        # survive, so a huge page cannot cut the provenance fence open.
        if len(text) > max_chars:
            text = text[:max_chars] + "\n…[截断]"
        fenced = wrap_untrusted(text, url)
        return f"HTTP {status}\n{fenced}"

    return AgentTool(
        name="web_fetch",
        description="抓取网页内容(受网络白名单约束)",
        handler=web_fetch,
        dimension="network",
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "max_chars": {"type": "integer"},
            },
            "required": ["url"],
        },
    )


__all__ = ["web_fetch_tool"]
