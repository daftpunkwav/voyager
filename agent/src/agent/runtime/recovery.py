"""Fault tolerance: retry / backoff / circuit breaking; checkpoint recovery
lives in state.py.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any


async def with_retry(
    fn: Callable[[], Awaitable[Any]],
    *,
    retries: int = 2,
    backoff: float = 0.1,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    no_retry_on: tuple[type[BaseException], ...] = (),
) -> Any:
    """Exponential backoff retry. The last failure is raised as-is; the caller decides by
    error code.

    Exceptions matching no_retry_on are not retried and raised immediately as-is: retrying a
    timeout only prolongs the wait, and retrying with an open breaker just spins idle.
    """
    delay = backoff
    for attempt in range(retries + 1):
        try:
            return await fn()
        except retry_on as exc:
            if attempt >= retries or isinstance(exc, no_retry_on):
                raise
            await asyncio.sleep(delay)
            delay *= 2


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    """Circuit breaker: after open_after consecutive failures, stay open for reset_after
    seconds (with automatic half-open probing).

    Counter and open/closed state reads/writes hold the lock: when multiple tasks share one
    breaker concurrently, failure counts no longer interleave across await gaps (concurrent
    successes swallowing failure counts would delay opening). fn itself runs without the lock.

    Half-open admits a single probe: after reset_after elapses only the first call enters
    fn, and concurrent calls fail fast with CircuitOpenError until that probe resolves
    (success closes the breaker; failure re-opens it for another reset_after). Without the
    gate, every queued caller would rush the dependency simultaneously — exactly the
    thundering herd the breaker exists to prevent. A cancelled probe (CancelledError is a
    BaseException, not an Exception) releases the probe slot without counting a failure:
    otherwise the slot would stay held forever and the breaker would never recover.
    """

    def __init__(self, *, open_after: int = 3, reset_after: float = 30.0) -> None:
        self._open_after = open_after
        self._reset_after = reset_after
        self._failures = 0
        self._opened_at = 0.0
        self._probing = False  # a half-open probe is in flight
        self._lock = threading.Lock()

    @property
    def open(self) -> bool:
        with self._lock:
            if self._opened_at and time.time() - self._opened_at >= self._reset_after:
                return False  # half-open: a probe may enter
            return self._opened_at > 0

    async def call(self, fn: Callable[[], Awaitable[Any]]) -> Any:
        with self._lock:
            if self._opened_at and time.time() - self._opened_at >= self._reset_after:
                if self._probing:  # one probe at a time in half-open
                    raise CircuitOpenError("circuit half-open: probe in flight, retry later")
                self._probing = True  # this call is the probe
            elif self._opened_at > 0:
                raise CircuitOpenError("circuit open, retry later")
        try:
            result = await fn()
        except Exception:
            with self._lock:
                self._probing = False
                self._failures += 1
                if self._failures >= self._open_after:
                    self._opened_at = time.time()
            raise
        except BaseException:
            # Cancellation etc. is not a dependency failure: release the probe
            # slot and re-raise. Swallowing it here would leave _probing set
            # forever, wedging the breaker in half-open.
            with self._lock:
                self._probing = False
            raise
        with self._lock:
            self._failures = 0
            self._opened_at = 0.0
            self._probing = False
        return result
