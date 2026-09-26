"""Tests for the overflow-recovery last resort: _emergency_truncate caps every
non-system message's content so a single huge entry cannot keep the transcript
over budget after the one aggressive compaction. Structure-preserving for
multi-modal list content (only oversized text parts are capped)."""

from agent.engine.modes.react import _emergency_truncate
from agent.llm import TextPart


def test_caps_long_string_content_and_keeps_short() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "x" * 5000},
        {"role": "user", "content": "short"},
    ]
    _emergency_truncate(messages, budget=800)  # cap = max(200, 200) = 200
    assert messages[0]["content"] == "sys"  # system is never touched
    assert messages[1]["content"].startswith("x" * 200)
    assert messages[1]["content"].endswith("…[上下文溢出截断]")
    assert messages[2]["content"] == "short"


def test_caps_only_oversized_text_parts_in_list_content() -> None:
    small = {"type": "text", "text": "keep me"}
    image = {"type": "image_url", "image_url": {"url": "data:image/png;base64,xxx"}}
    messages = [
        {
            "role": "user",
            "content": [TextPart(text="y" * 3000), small, image],
        }
    ]
    _emergency_truncate(messages, budget=400)
    parts = messages[0]["content"]
    head = parts[0]
    assert isinstance(head, TextPart)
    assert head.text.startswith("y" * 100)  # cap = max(200, budget//4) chars head
    assert head.text.endswith("…[上下文溢出截断]")
    assert parts[1] == small  # within-budget text part untouched
    assert parts[2] == image  # non-text parts pass through structurally
