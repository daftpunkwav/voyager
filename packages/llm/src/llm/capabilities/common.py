"""Shared mechanisms for the llm capability files: the domain Registry,
the injected Deps container, provider/key lookups, base_url validation and
the ProviderError -> ServiceError mapping.

Secret boundary: keys live in platform/secrets under key_name(provider_id);
provider dicts carry a has_api_key flag and never the key itself.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from platform_capability import Registry
from platform_contracts import (
    CONTEXT_OVERFLOW_HINT,
    ActorKind,
    ActorRef,
    ErrorSuffix,
    ServiceError,
)
from platform_secrets import SecretStore, SecretUnavailableError

from llm.client import (
    AuthError,
    ContextOverflowError,
    ProviderError,
    RateLimitError,
)
from llm.store import ProviderStore

DOMAIN = "llm"
registry = Registry(DOMAIN)


#: Per-model metadata fields (models_meta): booleans are capability flags,
#: ints are positive token budgets. Unknown keys are rejected so typos never
#: silently disable a feature the user believes is on.
_MODEL_META_BOOL_FIELDS = ("image_input", "audio_input", "video_input", "thinking")
_MODEL_META_INT_FIELDS = ("context_window", "max_output_tokens")


def valid_models_meta(meta: Any) -> bool:
    """Shape check for the models_meta map: {model_id: {field: value}}."""
    if not isinstance(meta, dict):
        return False
    for model, fields in meta.items():
        if not model or not isinstance(model, str) or not isinstance(fields, dict):
            return False
        for k, v in fields.items():
            if k in _MODEL_META_BOOL_FIELDS:
                if not isinstance(v, bool):
                    return False
            elif k in _MODEL_META_INT_FIELDS:
                if not isinstance(v, int) or isinstance(v, bool) or v <= 0:
                    return False
            else:
                return False
    return True


def service_error_for(exc: ProviderError) -> ServiceError:
    """Map ProviderError subclasses to ServiceError suffixes.

    Rate limit -> RATE_LIMITED, auth failure -> AUTH_REQUIRED, context
    overflow -> INVALID_INPUT (hinted CONTEXT_OVERFLOW_HINT so adapters can
    trigger compact-and-retry), anything else (5xx/network) -> UNAVAILABLE.
    The suffix drives the HTTP status and upstream degradation semantics, so
    callers can tell "retry later" apart from "change the request".
    """
    if isinstance(exc, RateLimitError):
        return ServiceError(DOMAIN, ErrorSuffix.RATE_LIMITED, f"LLM call failed: {exc}")
    if isinstance(exc, AuthError):
        return ServiceError(DOMAIN, ErrorSuffix.AUTH_REQUIRED, f"LLM call failed: {exc}")
    if isinstance(exc, ContextOverflowError):
        return ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            f"LLM call failed: {exc}",
            hint=CONTEXT_OVERFLOW_HINT,
        )
    return ServiceError(DOMAIN, ErrorSuffix.UNAVAILABLE, f"LLM call failed: {exc}")


@dataclass
class Deps:
    store: ProviderStore
    secrets: SecretStore
    settings: Any = None  # SettingsStore (hot-read embedding model); None in isolated tests


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps not injected: call init_deps() at service entry first")
    return _deps


def key_name(provider_id: str) -> str:
    return f"llm.provider.{provider_id}.api_key"


def with_key_flag(p: dict[str, Any], secrets: SecretStore) -> dict[str, Any]:
    return {**p, "has_api_key": secrets.has(key_name(p["id"]))}


def require_provider(pid: str) -> dict[str, Any]:
    p = require_deps().store.get(pid)
    if p is None:
        raise ServiceError(DOMAIN, ErrorSuffix.NOT_FOUND, f"Provider not found: {pid}")
    return p


def read_api_key(pid: str) -> str:
    """Read the provider key; missing key material degrades to an actionable
    ServiceError instead of a bare SecretUnavailableError.

    The secrets store needs SECRETS_ENCRYPTION_KEY on the machine. Without
    this conversion every chat turn dies on an unclassified exception that
    slips past the ServiceError-only degradation in the host LLM adapter and
    ends the turn silently for the user.
    """
    try:
        return require_deps().secrets.get(key_name(pid)) or ""
    except SecretUnavailableError:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.UNAVAILABLE,
            "Secret store unavailable: no key material configured on this machine",
            hint="Set SECRETS_ENCRYPTION_KEY in the repo-root .env and restart",
        ) from None


def _host_is_nonglobal(host: str) -> bool:
    """Loopback/private/link-local/non-global hosts, judged literally from the
    hostname without DNS resolution (keeps write-path calls non-blocking)."""
    h = (host or "").lower().rstrip(".")
    if h in {"localhost", "metadata.google.internal"} or h.endswith(".localhost"):
        return True
    try:
        addr = ipaddress.ip_address(h)
        mapped = getattr(addr, "ipv4_mapped", None)
        return not (mapped or addr).is_global
    except ValueError:
        return False


def validate_base_url(base_url: str, actor: ActorRef | None) -> str:
    """http(s) only. Private/loopback hosts are writable by USER actors alone
    (e.g. local Ollama); agents must not be able to send keys to intranets."""
    parsed = urlparse(base_url.strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.INVALID_INPUT,
            "base_url must be http(s) and include a hostname",
        )
    if _host_is_nonglobal(parsed.hostname) and (actor is None or actor.kind is not ActorKind.USER):
        raise ServiceError(
            DOMAIN,
            ErrorSuffix.FORBIDDEN,
            "Private/loopback base_url can only be configured by the user",
            hint="Configure local Ollama etc. in the settings page; agents must "
            "not send keys to intranets",
        )
    return base_url.strip()


__all__ = [
    "DOMAIN",
    "Deps",
    "init_deps",
    "key_name",
    "read_api_key",
    "registry",
    "require_deps",
    "require_provider",
    "service_error_for",
    "valid_models_meta",
    "validate_base_url",
    "with_key_flag",
]
