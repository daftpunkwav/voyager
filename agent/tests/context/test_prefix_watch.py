"""Tests for the prefix stability sentinel: the baseline turn is silent,
each later segment change logs one debug line, and tool order alone never
reads as a change."""

import logging

from agent.context.prefix_watch import PrefixWatch


def test_baseline_turn_is_silent(caplog) -> None:
    watch = PrefixWatch()
    with caplog.at_level(logging.DEBUG, logger="agent.context.prefix"):
        watch.observe(system="sys v1", tools=("a", "b"))
    assert caplog.records == []


def test_system_change_logs_one_line(caplog) -> None:
    watch = PrefixWatch()
    watch.observe(system="sys v1", tools=("a", "b"))
    with caplog.at_level(logging.DEBUG, logger="agent.context.prefix"):
        watch.observe(system="sys v2", tools=("a", "b"))
    assert len(caplog.records) == 1
    assert "system" in caplog.records[0].message


def test_tool_roster_change_logs_and_ignores_order(caplog) -> None:
    watch = PrefixWatch()
    watch.observe(system="s", tools=("a", "b"))
    with caplog.at_level(logging.DEBUG, logger="agent.context.prefix"):
        watch.observe(system="s", tools=("b", "a"))  # same roster, copied in another order
    assert caplog.records == []
    with caplog.at_level(logging.DEBUG, logger="agent.context.prefix"):
        watch.observe(system="s", tools=("a", "b", "c"))
    assert len(caplog.records) == 1
    assert "tool" in caplog.records[0].message


def test_identical_repeats_are_silent(caplog) -> None:
    watch = PrefixWatch()
    watch.observe(system="s", tools=("a",))
    with caplog.at_level(logging.DEBUG, logger="agent.context.prefix"):
        for _ in range(3):
            watch.observe(system="s", tools=("a",))
    assert caplog.records == []


# -- round-level cache health --------------------------------------------------


def _msgs(*contents: str) -> list[dict]:
    return [{"role": "user", "content": c} for c in contents]


def test_cold_start_is_not_a_break() -> None:
    watch = PrefixWatch()
    watch.observe(system="s", tools=("a",))
    watch.observe_round(input_tokens=5000, cached_tokens=0, messages=_msgs("a", "b"))
    assert watch.unexplained_misses == 0
    assert watch.cold_rounds == 1 and watch.warm_rounds == 0


def test_small_request_cold_round_is_not_a_break() -> None:
    watch = PrefixWatch()
    watch.observe(system="s", tools=("a",))
    watch.observe_round(input_tokens=900, cached_tokens=3000, messages=_msgs("a"))  # warm
    watch.observe_round(input_tokens=500, cached_tokens=0, messages=_msgs("a", "b"))
    assert watch.unexplained_misses == 0


def test_warm_then_cold_with_unchanged_head_is_unexplained(caplog) -> None:
    watch = PrefixWatch()
    watch.observe(system="s", tools=("a",))
    watch.observe_round(input_tokens=5000, cached_tokens=4000, messages=_msgs("a", "b"))
    with caplog.at_level(logging.WARNING, logger="agent.context.prefix"):
        watch.observe_round(input_tokens=5000, cached_tokens=0, messages=_msgs("a", "b"))
    assert watch.unexplained_misses == 1
    assert watch.last_break == {"kind": "unexplained", "input_tokens": 5000}
    assert any("no harness-visible head change" in r.message for r in caplog.records)


def test_warm_then_cold_after_head_move_is_explained() -> None:
    watch = PrefixWatch()
    watch.observe(system="s", tools=("a",))
    watch.observe_round(input_tokens=5000, cached_tokens=4000, messages=_msgs("a", "b"))
    # The head grew append-only (a new exchange landed): expected re-bill
    watch.observe_round(input_tokens=6000, cached_tokens=0, messages=_msgs("a", "b", "c"))
    assert watch.unexplained_misses == 0
    assert watch.changes["messages"] == 1
    assert watch.warm_rounds == 1 and watch.cold_rounds == 1


def test_warm_then_cold_after_segment_change_is_explained() -> None:
    """A turn-level system change consumed by the next cold round explains the
    re-bill; the pending flag is spent exactly once."""
    watch = PrefixWatch()
    watch.observe(system="s", tools=("a",))
    watch.observe_round(input_tokens=5000, cached_tokens=4000, messages=_msgs("a"))
    watch.observe(system="s v2", tools=("a",))  # turn boundary: system layer moved
    watch.observe_round(input_tokens=5000, cached_tokens=0, messages=_msgs("a"))
    assert watch.unexplained_misses == 0
    # A second cold round with no further change IS unexplained
    watch.observe_round(input_tokens=5000, cached_tokens=0, messages=_msgs("a"))
    assert watch.unexplained_misses == 1


def test_health_reports_counters() -> None:
    watch = PrefixWatch()
    watch.observe(system="s", tools=("a",))
    watch.observe_round(input_tokens=5000, cached_tokens=4000, messages=_msgs("a"))
    watch.observe_round(input_tokens=5000, cached_tokens=0, messages=_msgs("a"))
    health = watch.health()
    assert health["turns"] == 1
    assert health["warm_rounds"] == 1 and health["cold_rounds"] == 1
    assert health["unexplained_misses"] == 1
    assert health["head_changes"] == {"system": 0, "tools": 0, "messages": 0}
