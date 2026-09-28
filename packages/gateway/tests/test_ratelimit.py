"""RateLimiter unit behavior: sliding window, SSE slots, and the
tracked-actor cap (the window map must not grow without bound)."""

from collections import OrderedDict

import pytest
from gateway.ratelimit import _MAX_TRACKED_ACTORS, RateLimiter
from platform_contracts import ServiceError


def test_check_over_limit_raises_rate_limited() -> None:
    limiter = RateLimiter(per_minute=2)
    limiter.check("user")
    limiter.check("user")
    with pytest.raises(ServiceError) as exc:
        limiter.check("user")
    assert exc.value.body.code.endswith("RATE_LIMITED")


def test_window_map_bounded_by_tracked_actor_cap() -> None:
    """Distinct actor ids beyond the cap evict the least-recently-seen entry
    instead of growing the map without bound."""
    limiter = RateLimiter(per_minute=1000)
    for i in range(_MAX_TRACKED_ACTORS + 10):
        limiter.check(f"actor-{i}")
    assert len(limiter._hits) == _MAX_TRACKED_ACTORS
    # The oldest ids were evicted; the newest are all still tracked
    assert "actor-0" not in limiter._hits
    assert f"actor-{_MAX_TRACKED_ACTORS + 9}" in limiter._hits


def test_recently_seen_actor_survives_eviction() -> None:
    """A refresh of an existing entry (move_to_end) keeps an active actor from
    being evicted by a flood of one-shot ids."""
    limiter = RateLimiter(per_minute=1000)
    limiter.check("user")
    for i in range(_MAX_TRACKED_ACTORS):
        limiter.check(f"flood-{i}")
    limiter.check("user")  # refresh before the flood resumes
    for i in range(_MAX_TRACKED_ACTORS, _MAX_TRACKED_ACTORS + 5):
        limiter.check(f"flood-{i}")
    assert "user" in limiter._hits


def test_hits_map_is_insertion_ordered_for_eviction() -> None:
    """The eviction relies on OrderedDict semantics; pin the type so a
    refactor to a plain dict cannot silently reintroduce unbounded growth."""
    limiter = RateLimiter()
    limiter.check("a")
    assert isinstance(limiter._hits, OrderedDict)


def test_sse_slots_round_trip() -> None:
    limiter = RateLimiter(sse_max=1)
    limiter.acquire_sse()
    with pytest.raises(ServiceError):
        limiter.acquire_sse()
    limiter.release_sse()
    limiter.acquire_sse()
    assert limiter.sse_open == 1
