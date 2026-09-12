"""web_search tool: keyless search via the DuckDuckGo HTML endpoint
(baseline 2026-09).

The search endpoint URL passes the same policy whitelist as web_fetch — in
whitelist mode duckduckgo.com must be added to agent.network.domains.
Redirects are followed hop by hop with the policy + DNS guard re-checked on
every hop, switching to GET after the first redirect (the POST target must
not be re-submitted).
"""

from __future__ import annotations

import html as _html
import re
from urllib.parse import parse_qs, urlparse

import httpx
from platform_webguard.dns_pin import resolve_public
from platform_webguard.redirects import MAX_REDIRECTS, redirect_target

from agent.context.provenance import wrap_untrusted
from agent.policy import Action, PolicyEngine
from agent.tools.core.base import AgentTool

#: DuckDuckGo HTML endpoint (keyless search backend); update test stubs when
#: switching backends
_SEARCH_URL = "https://html.duckduckgo.com/html/"
_SEARCH_MAX_RESULTS = 8
#: Search request UA: the endpoint serves an abnormal page to script requests without a UA
_SEARCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    " (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

#: Search result entries: title link and snippet (current endpoint shape;
#: _parse_ddg_results returns [] when the shape changes)
_RESULT_A_RE = re.compile(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_SNIPPET_A_RE = re.compile(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _resolve_result_url(href: str) -> str:
    """DDG result links are mostly /l/?uddg=<encoded real URL> redirect shells;
    unwrap the real address."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "/l" in parsed.path:
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        if uddg:
            return uddg
    return href


def _strip_tags(fragment: str) -> str:
    return _html.unescape(_TAG_RE.sub("", fragment)).strip()


def _parse_ddg_results(page: str, limit: int) -> list[dict[str, str]]:
    """Parse results (title/url/snippet) from a DDG HTML page; returns []
    when the page shape changes."""
    titles = [(href, _strip_tags(body)) for href, body in _RESULT_A_RE.findall(page)]
    if not titles:
        return []
    snippets = [_strip_tags(s) for s in _SNIPPET_A_RE.findall(page)]
    out: list[dict[str, str]] = []
    for i, (href, title) in enumerate(titles[:limit]):
        out.append(
            {
                "title": title,
                "url": _resolve_result_url(href),
                "snippet": snippets[i] if i < len(snippets) else "",
            }
        )
    return out


def _format_results(query: str, results: list[dict[str, str]]) -> str:
    lines: list[str] = [f"[搜索] {query}"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r['title']}")
        lines.append(f"   {r['url']}")
        if r["snippet"]:
            lines.append(f"   {r['snippet']}")
    return "\n".join(lines)


def web_search_tool(policy: PolicyEngine | None = None) -> AgentTool:
    async def web_search(query: str, max_results: int = _SEARCH_MAX_RESULTS) -> str:
        query = query.strip()
        if not query:
            return "[参数无效] query 不能为空"
        limit = max(1, min(int(max_results), 10))
        url = _SEARCH_URL
        resp: httpx.Response | None = None
        async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
            # Same redirect handling as web_fetch: follow hop by hop manually,
            # re-check policy + DNS validation on every hop
            for _ in range(MAX_REDIRECTS):
                if policy is not None:
                    decision = policy.decide(Action(dimension="network", target=url))
                    if not decision.allow:
                        return f"[已拒绝] {decision.reason}"
                try:
                    await resolve_public(url)
                except ValueError as exc:
                    return f"[已拒绝] {exc}"
                if url == _SEARCH_URL:
                    resp = await client.post(
                        url,
                        data={"q": query},
                        headers={"User-Agent": _SEARCH_UA},
                    )
                else:  # switch to GET after a redirect (the POST target must not be re-submitted)
                    resp = await client.get(url, headers={"User-Agent": _SEARCH_UA})
                nxt = redirect_target(url, resp) if resp is not None else None
                if nxt is not None:
                    url = nxt  # every hop is re-checked: policy + DNS, above
                    continue
                break
        if resp is None or resp.status_code != 200:  # None: redirects exhausted, no final page
            status = resp.status_code if resp is not None else 0
            return f"[搜索失败] HTTP {status}: 重定向次数超限或无响应"
        results = _parse_ddg_results(resp.text, limit)
        if not results:
            return f"[无结果] {query}(端点形状可能变化,或被限流;可稍后重试或换 web_fetch 直取来源)"
        return wrap_untrusted(_format_results(query, results), f"搜索: {query}")

    return AgentTool(
        name="web_search",
        description=(
            "联网搜索(DuckDuckGo 后端,受网络白名单约束;"
            "whitelist 模式需将 duckduckgo.com 加入网络白名单)"
        ),
        handler=web_search,
        dimension="network",
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
            "required": ["query"],
        },
    )


__all__ = ["web_search_tool"]
