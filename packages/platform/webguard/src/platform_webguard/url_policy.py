"""SSRF URL policy: literal scheme/host checks and the intranet judgment
shared by every webguard consumer.

Covers loopback / link-local / reserved / RFC1918 private ranges but
**allows 198.18.0.0/15**: proxies such as Clash borrow that benchmark range
for fake-ip DNS, and intranet devices almost never occupy it; rejecting
"anything not public" would break fetching entirely behind such proxies.
IPv4-mapped IPv6 literals (::ffff:127.0.0.1) are unwrapped before checks.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

#: fake-ip proxy range (RFC 2544 benchmark): is_private is true but not a
#: real intranet, so allowed
FAKE_IP_NETS = (ipaddress.ip_network("198.18.0.0/15"),)


def as_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """Parse an IP; IPv4-mapped IPv6 is unwrapped to v4 before checks."""
    addr = ipaddress.ip_address(value)
    mapped = getattr(addr, "ipv4_mapped", None)
    return mapped if mapped is not None else addr


def is_internal(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True for real intranet addresses (loopback/link-local/reserved/RFC1918)."""
    if addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return True
    if any(addr in net for net in FAKE_IP_NETS):
        return False
    return addr.is_private


def is_internal_ip_str(value: str) -> bool:
    try:
        return is_internal(as_ip(value))
    except ValueError:
        return True  # unparseable counts as internal (reject, never allow)


def check_url_syntax(url: str) -> str:
    """http(s) + non-empty hostname; returns the hostname. ValueError with a
    model-actionable message otherwise (callers re-raise in their own error
    vocabulary, so this module stays domain-neutral)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https URLs are supported: {url}")
    host = parsed.hostname
    if not host:
        raise ValueError(f"URL is missing a hostname: {url}")
    return host


__all__ = ["FAKE_IP_NETS", "as_ip", "check_url_syntax", "is_internal", "is_internal_ip_str"]
