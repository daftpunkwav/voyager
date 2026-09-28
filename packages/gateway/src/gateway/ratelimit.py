"""Entry-point rate limiting (first layer): per-actor sliding window per
minute plus a cap on concurrent SSE connections.

Purely in-memory counters (rate-limit counts are state the gateway is
allowed to keep); configuration values are injected by the deployment
entry point. Over-limit requests raise GATEWAY.RATE_LIMITED (429),
matching the capability layer's CostQuota semantics.
"""

from __future__ import annotations

import time
from collections import OrderedDict, deque

from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "gateway"

#: Tracked-actor cap for the sliding-window map. Actor ids are deployment
#: facts (user, agent, system services), so in practice this is never hit; it
#: exists so a caller able to mint arbitrary ids cannot grow the process
#: without bound. Eviction is least-recently-seen: a flood of distinct ids
#: recycles entries among themselves, which only weakens throttle accuracy
#: under that flood (throttling is load control here, not an auth boundary).
_MAX_TRACKED_ACTORS = 1024


class RateLimiter:
    def __init__(self, per_minute: int = 600, sse_max: int = 8) -> None:
        self._per_minute = per_minute
        self._sse_max = sse_max
        self._hits: OrderedDict[str, deque[float]] = OrderedDict()
        self._sse_open = 0

    def check(self, actor_id: str) -> None:
        now = time.time()
        hits = self._hits.get(actor_id)
        if hits is None:
            if len(self._hits) >= _MAX_TRACKED_ACTORS:
                self._hits.popitem(last=False)  # least-recently-seen actor
            hits = deque()
            self._hits[actor_id] = hits
        else:
            self._hits.move_to_end(actor_id)
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
