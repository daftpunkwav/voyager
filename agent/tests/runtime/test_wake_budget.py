"""Wake budget: per-session consecutive wakeup counter. Real user input
resets; the cap degrades the next wakeup to a quiet notice."""

from __future__ import annotations

from agent.runtime.wake_budget import WakeBudget


def test_allows_up_to_cap_then_denies() -> None:
    b = WakeBudget()
    for _ in range(3):
        assert b.allow("s1") is True
        b.record("s1")
    assert b.allow("s1") is False


def test_sessions_are_independent() -> None:
    b = WakeBudget()
    for _ in range(3):
        b.record("s1")
    assert b.allow("s1") is False
    assert b.allow("s2") is True


def test_user_input_resets_the_chain() -> None:
    b = WakeBudget()
    for _ in range(3):
        b.record("s1")
    assert b.allow("s1") is False
    b.reset("s1")
    assert b.allow("s1") is True
