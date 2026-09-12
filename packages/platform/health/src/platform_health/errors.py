"""Unified error construction helpers.

Services raise; the agent decides by error code.
"""

from __future__ import annotations

from platform_contracts import ErrorSuffix, ServiceError


def unavailable(
    service: str,
    detail: str = "",
    *,
    hint: str = "retry later; if it stays unavailable, check the service status on the settings page",
    trace_id: str = "",
) -> ServiceError:
    """Service unavailable (503). The domain is the service name,
    e.g. ``example`` -> ``EXAMPLE.UNAVAILABLE``."""
    return ServiceError(
        service,
        ErrorSuffix.UNAVAILABLE,
        detail or f"{service} service is unavailable",
        hint=hint,
        trace_id=trace_id,
    )


def queue_full(
    service: str,
    detail: str = "",
    *,
    hint: str = "queue is full, please retry later",
    trace_id: str = "",
) -> ServiceError:
    """Service backpressure (429): over-limit callers are told to retry
    later instead of requests piling up."""
    return ServiceError(
        service,
        ErrorSuffix.QUEUE_FULL,
        detail or f"{service} queue is full",
        hint=hint,
        trace_id=trace_id,
    )
