"""Web submodule capabilities: URL clipping (fetch or manual entry) /
list / metadata / removal.

save_url guards against SSRF with a resolve-and-pin scheme: each hop
performs exactly one DNS resolution inside this module, validates every
resolved address as public, then connects straight to that IP (TLS uses
the original hostname for SNI and certificate verification, and the Host
header keeps the original hostname). Subsequent connections use the IP
literal with no second resolution -- closing the DNS rebinding window of
"validate once, then connect with a fresh resolution".
"""

from __future__ import annotations

import ipaddress
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import ParseResult, urlparse

import httpx
from platform_capability import Registry, capability
from platform_contracts import ActorKind, ActorRef, DomainEvent, ErrorSuffix, Event, ServiceError
from platform_eventbus import EventBus
from platform_webguard.body import read_bounded
from platform_webguard.dns_pin import default_resolver, literal_ips, pinned_request
from platform_webguard.url_policy import as_ip, check_url_syntax, is_internal

from .._shared.events import with_session
from .store import WebStore, html_to_text, valid_tag

_DOMAIN = "sources"
registry = Registry(_DOMAIN)

_MAX_REDIRECTS = 3
#: Absolute body read cap: a timeout bounds duration, not size, and the
#: page store must not buffer unbounded content from a whitelisted host.
_MAX_BODY_BYTES = 2_000_000

#: Resolver type: (host, port) -> all resolved IP strings; tests inject
#: fakes so the suite stays offline
ResolverFn = Callable[[str, int], Awaitable[list[str]]]

_WEB_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.web")


async def _default_resolver(host: str, port: int) -> list[str]:
    return await default_resolver(host, port)


def _as_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    return as_ip(value)


def _reject_nonglobal(host: str, ips: list[str]) -> None:
    """Shared SSRF policy (platform_webguard) with this domain's error
    vocabulary; any non-global candidate counts as DNS rebinding."""
    for ip in ips:
        if is_internal(_as_ip(ip)):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.FORBIDDEN,
                f"Target is not in public address space: {host}({ip})",
                hint="Private/loopback/link-local addresses are rejected by SSRF protection",
            )


def _assert_pinnable(url: str) -> tuple[ParseResult, list[str]]:
    """Syntax-level plus address-level validation (shared webguard policy):
    http(s) only, non-empty hostname, every literal address globally routable.
    Non-literal hostnames resolve inside save_url; this function checks
    syntax and literals so unit tests can reuse the checks offline."""
    try:
        host = check_url_syntax(url)
    except ValueError as exc:
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, str(exc)) from None
    parsed = urlparse(url)
    ips = literal_ips(host)
    if ips is None:
        return parsed, []
    _reject_nonglobal(host, ips)
    return parsed, ips


@dataclass
class WebDeps:
    store: WebStore
    bus: EventBus | None
    resolve: ResolverFn = field(default_factory=lambda: _default_resolver)


_deps: WebDeps | None = None


def init_deps(deps: WebDeps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> WebDeps:
    if _deps is None:
        raise RuntimeError("deps not injected: call init_deps() at the service entry point first")
    return _deps


def _require_page(page_id: str) -> dict[str, Any]:
    page = _require_deps().store.get(page_id)
    if page is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"Page not found: {page_id}")
    return page


async def _fetch_pinned(
    client: httpx.AsyncClient, url: str, *, max_bytes: int = _MAX_BODY_BYTES
) -> tuple[httpx.Response, bytes]:
    """Fetch one hop: single resolution -> validate all as public ->
    request the validated IP directly. Returns the response (status and
    headers stay readable after close) and the body read under ``max_bytes``
    so a huge page cannot exhaust memory.

    For https the original hostname goes into the sni_hostname extension
    (httpx/httpcore convention) so the certificate is verified against it;
    the Host header keeps the original hostname, so server-side routing is
    unaffected by the IP rewrite.
    """
    deps = _require_deps()
    parsed, literal = _assert_pinnable(url)
    host = parsed.hostname
    if host is None:  # unreachable: _assert_pinnable already rejected hostless URLs
        raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"URL is missing a hostname: {url}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    ips = literal if literal else await deps.resolve(host, port)
    if not ips:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.UNAVAILABLE, f"Hostname resolves to no address: {host}"
        )
    _reject_nonglobal(host, ips)
    request = pinned_request(client, url, ips[0])
    resp = await client.send(request, stream=True)
    body = await read_bounded(resp, max_bytes)
    return resp, body


@capability(
    registry,
    name="save_url",
    description="Fetch a web page's content into the library (per-hop DNS-pinned SSRF protection)",
    cost=3,
    # The agent-facing fetch obeys the same network policy as the native
    # web tools: the bridge passes this through so prompt-injected fetches
    # cannot bypass the user's network allowlist.
    dimension="network",
)
async def save_url(
    url: str, title: str = "", tags: list[str] | None = None, category: str = ""
) -> dict:
    deps = _require_deps()
    for tag in list(tags or []):
        if not valid_tag(tag):
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INVALID_INPUT,
                f"Invalid tag: {tag} (max 32 chars; forbidden \\\"\\',[] characters)",
            )
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            # Follow redirects hop by hop; each hop re-runs the
            # resolve-validate-pin flow (blocks external page 302 -> intranet)
            for _ in range(_MAX_REDIRECTS):
                resp, body = await _fetch_pinned(client, url)
                if resp.is_redirect and resp.has_redirect_location:
                    url = str(httpx.URL(url).join(resp.headers.get("location", "")))
                    continue
                break
            resp.raise_for_status()
    except ServiceError:
        raise
    except Exception as exc:
        raise ServiceError(
            _DOMAIN, ErrorSuffix.UNAVAILABLE, f"Fetch failed: {type(exc).__name__}: {exc}"
        ) from exc
    charset = resp.charset_encoding or "utf-8"
    try:
        html = body.decode(charset, errors="replace")
    except LookupError:
        # Hostile/broken Content-Type charset name (raised outside the fetch
        # try above): utf-8 with replacement keeps the clip alive
        html = body.decode("utf-8", errors="replace")
    page_title, text, images = html_to_text(html)
    domain = urlparse(url).hostname or ""
    final_title = title.strip() or page_title or url
    pid = deps.store.add(
        {
            "title": final_title[:200],
            "url": url,
            "domain": domain,
            "summary": text[:300],
            "content": text,
            "tags": list(tags or []),
            "category": category,
            "meta": {"images": images, "chars": len(text)},
        }
    )
    if deps.bus is not None:
        await deps.bus.publish(
            Event(
                type=DomainEvent.SOURCE_ADDED,
                actor=_WEB_ACTOR,
                payload=with_session({"source_id": pid, "kind": "web", "title": final_title}),
            )
        )
        await deps.bus.publish(
            Event(
                type=DomainEvent.SOURCE_READY,
                actor=_WEB_ACTOR,
                payload=with_session({"source_id": pid, "kind": "web", "title": final_title}),
            )
        )
    return _require_page(pid)


@capability(
    registry,
    name="add_page",
    description="Manually add a web clipping (title + content; use save_url to fetch)",
)
async def add_page(
    title: str, content: str = "", url: str = "", tags: list[str] | None = None, category: str = ""
) -> dict:
    deps = _require_deps()
    for tag in list(tags or []):
        if not valid_tag(tag):
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"Invalid tag: {tag}")
    domain = urlparse(url).hostname or "" if url else ""
    pid = deps.store.add(
        {
            "title": title[:200],
            "url": url,
            "domain": domain,
            "summary": content[:300],
            "content": content,
            "tags": list(tags or []),
            "category": category,
            "meta": {"chars": len(content)},
        }
    )
    if deps.bus is not None:
        await deps.bus.publish(
            Event(
                type=DomainEvent.SOURCE_ADDED,
                actor=_WEB_ACTOR,
                payload=with_session({"source_id": pid, "kind": "web", "title": title}),
            )
        )
    return _require_page(pid)


@capability(
    registry,
    name="list_pages",
    description="Web page list (summaries; query matches title/content, tag filter)",
    write=False,
)
def list_pages(query: str = "", tag: str = "", limit: int = 50) -> list[dict]:
    return _require_deps().store.list(query=query.strip(), tag=tag.strip(), limit=limit)


@capability(
    registry, name="get_page", description="Fetch a page's full text on demand", write=False
)
def get_page(page_id: str) -> dict:
    item = _require_deps().store.get(page_id)
    if item is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"Page not found: {page_id}")
    return item


@capability(
    registry,
    name="set_page_meta",
    description="Set page title/tags/category (aligned with set_repo_meta)",
)
def set_page_meta(
    page_id: str,
    title: str | None = None,
    tags: list[str] | None = None,
    category: str | None = None,
) -> dict:
    deps = _require_deps()
    item = deps.store.get(page_id)
    if item is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"Page not found: {page_id}")
    for tag in list(tags or []):
        if not valid_tag(tag):
            raise ServiceError(_DOMAIN, ErrorSuffix.INVALID_INPUT, f"Invalid tag: {tag}")
    deps.store.set_meta(page_id, title=title, tags=tags, category=category)
    return _require_page(page_id)


@capability(registry, name="remove_page", description="Delete a web clipping", reversible=False)
async def remove_page(page_id: str) -> dict:
    deps = _require_deps()
    item = deps.store.get(page_id)
    if item is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"Page not found: {page_id}")
    deps.store.remove(page_id)
    if deps.bus is not None:
        await deps.bus.publish(
            Event(
                type=DomainEvent.SOURCE_REMOVED,
                actor=_WEB_ACTOR,
                payload=with_session({"source_id": page_id, "kind": "web", "title": item["title"]}),
            )
        )
    return {"removed": page_id, "title": item["title"]}
