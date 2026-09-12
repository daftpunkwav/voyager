"""Editor shrink guard: a summary that would not be smaller than the content
it replaces is refused — the source segments stay verbatim."""

from __future__ import annotations

from agent.context.editor import apply_plan


def _msg(role: str, text: str) -> dict:
    return {"role": role, "content": text}


def test_shrink_guard_refuses_growth() -> None:
    """The summary is longer than the summarized span: keep the span."""
    messages = [_msg("user", "x" * 30)]
    segments = [(0, 1)]
    plan = {"summarize": [0], "summary": "y" * 100}
    out = apply_plan(messages, segments, plan)
    assert out == messages  # verbatim, no summary row landed


def test_summary_smaller_than_source_is_applied() -> None:
    messages = [_msg("user", "a" * 500), _msg("assistant", "b" * 500)]
    segments = [(0, 2)]
    plan = {"summarize": [0], "summary": "short"}  # segment 0 spans both messages
    out = apply_plan(messages, segments, plan)
    assert len(out) == 1 and "short" in out[0]["content"]


def test_boundary_equality_refuses() -> None:
    """Summary length equal to the source (plus marker) is not a shrink."""
    messages = [_msg("user", "x" * 100)]
    plan = {"summarize": [0], "summary": "y" * 100}
    out = apply_plan(messages, [(0, 1)], plan)
    assert out == messages
