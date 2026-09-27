"""Request-time egress pinning for provider base_urls.

The write path (add_provider / update_provider) validates base_url syntax and
records whether the target is a USER-authorized private endpoint. This module
completes the defense at request time: resolve the host once, validate, and
hand back the IP the connection must use (resolve-then-connect gap closed,
so DNS rebinding cannot retarget the request between validation and dial).

USER-authorized private endpoints (local Ollama / vLLM) are resolved but
never rejected — they are the documented BYOK deployment shape. Every other
target must resolve to a public address. Failure detail (which intranet IP
came back) goes to the log, not into the ServiceError an agent can read.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from platform_contracts import ErrorSuffix, ServiceError
from platform_webguard import default_resolver, literal_ips, resolve_public

log = logging.getLogger("llm.net_pin")


async def pinned_ip(provider: dict[str, Any]) -> str:
    """Resolve the provider host once; return the validated IP the request
    must connect to. Raises ServiceError when resolution fails or a public
    endpoint resolves into private space (detail in the log only)."""
    url = str(provider.get("base_url") or "")
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    literal = literal_ips(host)
    if provider.get("private_endpoint") or literal is not None:
        # USER-authorized private endpoint (or an IP literal, which pins to
        # itself): resolve but do not reject private answers.
        try:
            ips = literal if literal is not None else await default_resolver(host, port)
        except OSError as exc:
            log.warning("provider host resolution failed for %s: %s", host, exc)
            raise ServiceError(
                "llm",
                ErrorSuffix.UNAVAILABLE,
                f"provider host could not be resolved: {host}",
                hint="Check the base_url in the settings page",
            ) from None
        if not ips:
            raise ServiceError(
                "llm",
                ErrorSuffix.UNAVAILABLE,
                f"provider host resolves to no address: {host}",
                hint="Check the base_url in the settings page",
            )
        return ips[0]
    try:
        return await resolve_public(url)
    except ValueError as exc:
        # The raw ValueError names the intranet IP it resolved to; that
        # detail stays in the log, the agent gets a generic refusal.
        log.warning("provider base_url rejected: %s", exc)
        raise ServiceError(
            "llm",
            ErrorSuffix.FORBIDDEN,
            "provider endpoint does not resolve to a public address",
            hint="Public providers must use https and a public DNS name; "
            "configure local servers (Ollama etc.) through the settings page",
        ) from None
