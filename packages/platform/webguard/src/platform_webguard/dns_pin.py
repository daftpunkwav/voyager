"""DNS resolve-and-pin: resolve once, validate every candidate as public,
and (for the pinning consumer) rewrite the request onto the validated IP so
the connection cannot drift to a different address (DNS rebinding).

Two consumer levels:
- validate-only (agent web tools): resolve and refuse intranet answers;
- full pinning (sources save_url): also rewrite the httpx request host to
  the chosen IP, keeping the original hostname in the Host header and the
  TLS sni_hostname so certificates and routing stay correct.
"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlparse

import httpx

from .url_policy import as_ip, check_url_syntax, is_internal

#: (host, port) -> all resolved IP strings; tests inject fakes so suites
#: stay offline
ResolverFn = Callable[[str, int], Awaitable[list[str]]]


async def default_resolver(host: str, port: int) -> list[str]:
    """loop.getaddrinfo runs off the event loop (never blocking it); dedupes
    while keeping order."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    seen: list[str] = []
    for info in infos:
        ip = str(as_ip(str(info[4][0])))
        if ip not in seen:
            seen.append(ip)
    return seen


def literal_ips(host: str) -> list[str] | None:
    """The host itself when it is an IP literal (resolver bypassed; it pins
    to itself); None for hostnames."""
    try:
        return [str(as_ip(host))]
    except ValueError:
        return None


def reject_nonglobal(host: str, ips: list[str], *, error: type[Exception]) -> None:
    """Raise `error` if any candidate is non-global (loopback/link-local mixed
    into dual-stack answers counts as DNS rebinding)."""
    for ip in ips:
        if is_internal(as_ip(ip)):
            raise error(
                f"{host} resolves to a non-public address {ip}; "
                "private/loopback/link-local targets are rejected by SSRF protection"
            )


async def resolve_public(url: str, *, resolver: ResolverFn | None = None) -> str:
    """Resolve the URL's host and return one validated public IP; ValueError
    on syntax/intranet answers (callers map it into their error vocabulary).
    Literal-IP hosts skip the resolver and validate directly."""
    from .url_policy import is_internal_ip_str

    host = check_url_syntax(url)
    port = urlparse(url).port or (443 if url.startswith("https") else 80)
    ips = literal_ips(host)
    if ips is None:
        resolve = resolver or default_resolver
        try:
            ips = await resolve(host, port)
        except OSError as exc:
            # Failing closed: returning the raw hostname here would send an
            # unvalidated string back as if it were the pinned IP, reopening
            # the rebinding window on a second resolution. Callers surface
            # ValueError in their own error vocabulary.
            raise ValueError(f"DNS resolution failed for {host}: {exc}") from exc
    if not ips:
        raise ValueError(f"{host} resolves to no address")
    for ip in ips:
        if is_internal_ip_str(ip):
            raise ValueError(
                f"{host} resolves to an intranet address {ip}; "
                "whitelisted domains must not point at private networks"
            )
    return ips[0]


def pinned_request(client: httpx.AsyncClient, url: str, chosen_ip: str) -> httpx.Request:
    """Build an httpx request rewritten onto the validated IP (full-pinning
    consumers only): original hostname stays in the Host header and, for
    https, in the sni_hostname extension so certificate verification and
    server-side routing are unaffected by the IP rewrite."""
    parsed = urlparse(url)
    request = client.build_request("GET", httpx.URL(url).copy_with(host=chosen_ip))
    request.headers["host"] = parsed.netloc
    if parsed.scheme == "https":
        request.extensions["sni_hostname"] = parsed.hostname or ""
    return request


__all__ = [
    "ResolverFn",
    "default_resolver",
    "literal_ips",
    "pinned_request",
    "reject_nonglobal",
    "resolve_public",
]
