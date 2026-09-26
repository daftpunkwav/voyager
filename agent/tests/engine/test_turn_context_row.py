"""Tests for the trailing per-turn context row refresh on mid-turn resume:
in-place swap for snapshots that carry the row, and marker-preserving fold
into a trailing user entry for legacy (pre-feature) snapshots — never a
second consecutive user message (strict anthropic-format endpoints reject
those and the client does not merge them)."""

from agent.context.builder import TURN_CONTEXT_HEADER
from agent.engine.turn import _refresh_turn_context_row


def _row() -> dict:
    return {"role": "user", "content": f"{TURN_CONTEXT_HEADER}\n\n窗口 12% | 摘要..."}


def test_swaps_existing_row_in_place() -> None:
    old = {"role": "user", "content": f"{TURN_CONTEXT_HEADER}\n\n旧状态"}
    messages: list[dict] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "任务"},
        old,
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}]},
        {"role": "tool", "tool_call_id": "a", "content": "r"},
    ]
    _refresh_turn_context_row(messages, _row())
    assert len(messages) == 5  # replaced, not appended
    assert messages[2]["content"].startswith(TURN_CONTEXT_HEADER)
    assert "旧状态" not in messages[2]["content"]


def test_folds_into_trailing_user_entry_never_second_user_row() -> None:
    """Legacy snapshot ending on the turn's input user entry: the fresh row
    folds INTO it (marker first), keeping a single user message."""
    messages: list[dict] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "查一下目录"},
    ]
    _refresh_turn_context_row(messages, _row())
    assert len(messages) == 2  # no second user message
    folded = messages[1]
    assert folded["content"].startswith(TURN_CONTEXT_HEADER)  # marker stays recognizable
    assert "查一下目录" in folded["content"]  # the input survives inside the fold


def test_appends_after_tool_tail_where_adjacency_is_legal() -> None:
    messages: list[dict] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "任务"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}]},
        {"role": "tool", "tool_call_id": "a", "content": "r"},
    ]
    _refresh_turn_context_row(messages, _row())
    assert messages[-1] is not None and messages[-1]["content"].startswith(TURN_CONTEXT_HEADER)
    assert len(messages) == 5


def test_assistant_echoing_marker_is_never_replaced() -> None:
    marker_echo = {
        "role": "assistant",
        "content": f"{TURN_CONTEXT_HEADER} 也许可以这样",
        "tool_calls": [{"id": "a"}],
    }
    messages: list[dict] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "任务"},
        marker_echo,
        {"role": "tool", "tool_call_id": "a", "content": "r"},
    ]
    _refresh_turn_context_row(messages, _row())
    assert messages[2] is marker_echo  # untouched
    assert messages[-1]["content"].startswith(TURN_CONTEXT_HEADER)  # appended after the tool row


def test_none_row_keeps_snapshot_unchanged() -> None:
    messages: list[dict] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "任务"},
    ]
    _refresh_turn_context_row(messages, None)
    assert len(messages) == 2
