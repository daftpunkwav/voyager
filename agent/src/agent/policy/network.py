"""Network dimension: mode policy, the literal-host intranet check, and
the decision function.

Order of checks is frozen: off -> non-global literal -> all/whitelist. Even
the ALL mode must not hit loopback/intranet literals (SSRF), and a whitelist
entry cannot override that.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse

from agent.policy.decision import Decision
from agent.policy.levels import Level

NET_OFF, NET_WHITELIST, NET_ALL = "off", "whitelist", "all"

# Network mode strictness, most-strict first: off (0) < whitelist (1) < all (2);
# narrowing keeps the smaller (stricter) value.
_NET_STRICTNESS = {NET_OFF: 0, NET_WHITELIST: 1, NET_ALL: 2}


def narrow_network(global_mode: str, requested: str) -> str:
    """Narrow the network mode: combine a subagent's requested mode with the global mode,
    taking the stricter one."""
    if _NET_STRICTNESS.get(requested, _NET_STRICTNESS[NET_WHITELIST]) < _NET_STRICTNESS.get(
        global_mode, _NET_STRICTNESS[NET_WHITELIST]
    ):
        return requested
    return global_mode


@dataclass(frozen=True)
class NetworkPolicy:
    mode: str = NET_WHITELIST
    domains: tuple[str, ...] = ("github.com", "arxiv.org")


def host_is_nonglobal(host: str) -> bool:
    """Literal checks for loopback/intranet/link-local/localhost names; only
    inspects the host as written in the URL, no DNS. The literal rules mirror
    the same check in packages/llm (no cross-package import), but the network
    dimension has no USER exception: web_fetch hitting 127.0.0.1 is SSRF and
    is always rejected. An empty host (parse failure) does not count as
    non-global."""
    h = (host or "").lower().rstrip(".")
    if h in {"localhost", "metadata.google.internal"} or h.endswith(".localhost"):
        return True
    try:
        addr = ipaddress.ip_address(h)
        mapped = getattr(addr, "ipv4_mapped", None)
        return not (mapped or addr).is_global
    except ValueError:
        return False


def decide_network(net: NetworkPolicy, action) -> Decision:
    # urlparse.hostname: strips port and userinfo (https://evil.com@github.com/ actually
    # connects to evil.com) and lowercases; bare domains (no scheme) are handled as-is
    host = (urlparse(action.target).hostname or "") if "://" in action.target else action.target
    host = host.lower()
    if net.mode == NET_OFF:
        return Decision(
            False, reason="Network access: off (switch to whitelist or full in settings)"
        )
    # Non-global literals are checked before the mode branches: even the ALL mode must
    # not hit loopback/intranet (SSRF), and a whitelist entry cannot override this
    if host_is_nonglobal(host):
        return Decision(False, reason="Network access: loopback or private addresses rejected")
    if net.mode == NET_ALL:
        return Decision(True, Level.L1_NOTIFY, "Full network access")
    if any(host == d or host.endswith("." + d) for d in net.domains):
        return Decision(True, Level.L1_NOTIFY, f"Allowlisted domain: {host}")
    return Decision(
        False, reason=f"Domain not in the allowlist: {host} (add it in the settings page)"
    )


__all__ = [
    "NET_ALL",
    "NET_OFF",
    "NET_WHITELIST",
    "NetworkPolicy",
    "decide_network",
    "host_is_nonglobal",
    "narrow_network",
]
