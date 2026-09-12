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
