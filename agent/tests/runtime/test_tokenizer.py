"""Tests for token estimation: CJK counted per character, Latin at 4 chars per
token, per-message frame overhead.
"""

import json
from typing import Any

from agent.runtime.tokenizer import estimate_messages, estimate_text


class TestEstimateText:
    def test_empty(self) -> None:
        assert estimate_text("") == 0

    def test_cjk_one_per_char(self) -> None:
        assert estimate_text("上下文工程") == 5

    def test_latin_four_chars_per_token(self) -> None:
        assert estimate_text("abcdefgh") == 2

    def test_latin_ceil(self) -> None:
        assert estimate_text("abc") == 1

    def test_mixed(self) -> None:
        # 2 CJK chars + 3 Latin chars: 2 + ceil(3/4) = 3
        assert estimate_text("中文abc") == 3


class TestEstimateMessages:
    def test_floor_per_message(self) -> None:
        # Empty content still pays the per-message frame overhead floor
        assert estimate_messages([{"role": "user", "content": ""}]) == 4

    def test_content_counted(self) -> None:
        msgs = [{"role": "user", "content": "一" * 10}]
        assert estimate_messages(msgs) == 10

    def test_tool_calls_arguments_counted(self) -> None:
        """Arguments JSON of assistant.tool_calls is counted (ignoring it skews multi-tool turns)."""
        calls = [{"id": "1", "name": "t", "arguments": {"path": "a" * 100}}]
        msgs = [{"role": "assistant", "content": "", "tool_calls": calls}]
        bare = estimate_messages([{"role": "assistant", "content": ""}])
        assert estimate_messages(msgs) > bare + len(json.dumps(calls)) // 8

    def test_emoji_and_newlines(self) -> None:
        """Emoji (wide chars), newlines, and mixed content estimate sanely; newlines are narrow chars."""
        assert estimate_text("😀😀") == 2
        assert estimate_text("一\n二\n") == 3  # 2 CJK + ceil(2 newlines / 4) = 3
        assert estimate_text("中文 english 混排") > 0

    def test_non_json_serializable_tool_calls(self) -> None:
        """Non-JSON-serializable objects in arguments: the default=str fallback must not raise."""
        calls = [{"id": "1", "name": "t", "arguments": {"obj": object()}}]
        msgs = [{"role": "assistant", "content": "", "tool_calls": calls}]
        assert estimate_messages(msgs) > 0

    def test_echoed_thinking_counted(self) -> None:
        """Echoed thinking blocks ride every request while tool use continues;
        ignoring them would skew budgets on thinking-model turns."""
        base = [{"role": "assistant", "content": "", "tool_calls": []}]
        thinking = "weigh options carefully"
        msgs = [
            {
                "role": "assistant",
                "content": "",
                "thinking_blocks": [{"type": "thinking", "thinking": thinking}],
            }
        ]
        assert estimate_messages(msgs) > estimate_messages(base)

    def test_malformed_thinking_ignored(self) -> None:
        """Non-list thinking_blocks or non-string thinking never raises."""
        msgs: list[dict[str, Any]] = [
            {"role": "assistant", "content": "hi", "thinking_blocks": "junk"},
            {"role": "assistant", "content": "hi", "thinking_blocks": [{"type": "thinking"}]},
        ]
        assert estimate_messages(msgs) == 2 * estimate_messages(
            [{"role": "assistant", "content": "hi"}]
        )
