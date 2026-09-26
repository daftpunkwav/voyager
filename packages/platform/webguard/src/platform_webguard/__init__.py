"""Shared URL safety guard (webguard): SSRF policy, DNS resolve-and-pin and
per-hop redirect checks — the single implementation behind the agent's web
tools and the sources domain's page importer.

Two consumers, two levels (both satisfy "a second implementation means split
the seam"): validate-only resolution for the agent's web_fetch/web_search,
full request pinning for sources save_url. Zero business vocabulary: errors
surface as ValueError/Exception subclasses the callers translate.

The re-exports below are the package's public surface: consumers import from
``platform_webguard`` directly, so the internal module layout (body / dns_pin /
redirects / url_policy) stays free to change without touching either domain.
"""

from .body import read_bounded
from .dns_pin import default_resolver, literal_ips, pinned_request, resolve_public
from .redirects import MAX_REDIRECTS, redirect_target
from .url_policy import as_ip, check_url_syntax, is_internal

__all__ = [
    "MAX_REDIRECTS",
    "as_ip",
    "check_url_syntax",
    "default_resolver",
    "is_internal",
    "literal_ips",
    "pinned_request",
    "read_bounded",
    "redirect_target",
    "resolve_public",
]
