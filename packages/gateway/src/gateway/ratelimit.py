"""Entry-point rate limiting (first layer): per-actor sliding window per
minute plus a cap on concurrent SSE connections.

Purely in-memory counters (rate-limit counts are state the gateway is
allowed to keep); configuration values are injected by the deployment
entry point. Over-limit requests raise GATEWAY.RATE_LIMITED (429),
matching the capability layer's CostQuota semantics.
"""

from __future__ import annotations

import time
from collections import deque

from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "gateway"


class RateLimiter:
    def __init__(self, per_minute: int = 600, sse_max: int = 8) -> None:
        self._per_minute = per_minute
        self._sse_max = sse_max
        self._hits: dict[str, deque[float]] = {}
        self._sse_open = 0

    def check(self, actor_id: str) -> None:
        now = time.time()
        hits = self._hits.setdefault(actor_id, deque())
        while hits and now - hits[0] > 60.0:
            hits.popleft()
        if len(hits) >= self._per_minute:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.RATE_LIMITED,
                f"Too many requests: {actor_id} limit is {self._per_minute}/minute",
                hint="Retry later; see the gateway.rate_limit.per_minute setting",
            )
        hits.append(now)

    def acquire_sse(self) -> None:
        if self._sse_open >= self._sse_max:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.RATE_LIMITED,
                f"SSE connection limit reached ({self._sse_max})",
                hint="Close stream connections on other pages, then retry",
            )
        self._sse_open += 1

    def release_sse(self) -> None:
        self._sse_open = max(0, self._sse_open - 1)

    @property
    def sse_open(self) -> int:
        return self._sse_open
