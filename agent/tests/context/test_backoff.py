"""Tests for the compaction backoff guard: suppression after repeated LLM
failures, geometric window growth with a cap, and reset on success."""

from agent.context.backoff import CompactionBackoff


def test_single_failure_suppresses_nothing() -> None:
    guard = CompactionBackoff()
    guard.record(plan_applied=False)
    assert guard.allow_llm()  # below the threshold the planner is retried


def test_suppression_starts_at_threshold_and_grows() -> None:
    guard = CompactionBackoff()
    guard.record(plan_applied=False)
    guard.record(plan_applied=False)  # threshold reached: window 1
    assert guard.allow_llm() is False
    assert guard.allow_llm() is True  # window exhausted: planner retried
    guard.record(plan_applied=False)  # still failing: window 2
    assert guard.allow_llm() is False
    assert guard.allow_llm() is False
    assert guard.allow_llm() is True


def test_window_growth_is_capped() -> None:
    guard = CompactionBackoff(cap=2)
    for _ in range(6):
        guard.record(plan_applied=False)
    assert not guard.allow_llm() and not guard.allow_llm()
    assert guard.allow_llm()  # window never exceeds the cap
    guard.record(plan_applied=False)
    assert not guard.allow_llm() and not guard.allow_llm()
    assert guard.allow_llm()


def test_success_resets_the_guard() -> None:
    guard = CompactionBackoff()
    guard.record(plan_applied=False)
    guard.record(plan_applied=False)
    assert guard.allow_llm() is False
    guard.record(plan_applied=True)  # an applied plan clears everything
    assert guard.allow_llm() is True
    guard.record(plan_applied=False)  # a fresh failure starts from zero
    assert guard.allow_llm() is True


def test_suppressed_attempts_record_nothing() -> None:
    """Mechanical compactions while suppressed must not advance the failure
    count: they prove nothing about the planner."""
    guard = CompactionBackoff()
    guard.record(plan_applied=False)
    guard.record(plan_applied=False)
    guard.allow_llm()  # suppressed attempt (would-be mechanical) - no record
    assert guard.allow_llm() is True
