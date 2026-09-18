"""Unit tests for multi-modal ContentPart support across protocol, wire translation,
and token estimation.
"""

from __future__ import annotations

from typing import Any

from agent.context.compressor import compress
from agent.context.tokenizer import estimate_messages
from agent.llm import FilePart, ImagePart, TextPart, content_to_text
from agent.llm_http import _messages_to_wire


def test_content_part_dataclasses() -> None:
    text_p = TextPart(text="Hello world")
    assert text_p.type == "text"
    assert text_p.text == "Hello world"

    img_p = ImagePart(url="https://example.com/test.png", detail="high")
    assert img_p.type == "image_url"
    assert img_p.url == "https://example.com/test.png"
    assert img_p.detail == "high"

    file_p = FilePart(filename="doc.pdf", data="base64...", mime_type="application/pdf")
    assert file_p.type == "file"
    assert file_p.filename == "doc.pdf"


def test_content_to_text() -> None:
    assert content_to_text("") == ""
    assert content_to_text("pure string") == "pure string"

    parts: list[Any] = [
        TextPart(text="First paragraph"),
        ImagePart(url="https://example.com/image.png"),
        TextPart(text="Second paragraph"),
    ]
    assert content_to_text(parts) == "First paragraph\nSecond paragraph"

    dict_parts = [
        {"type": "text", "text": "Dict paragraph 1"},
        {"type": "image_url", "image_url": {"url": "data:..."}},
        {"type": "text", "text": "Dict paragraph 2"},
    ]
    assert content_to_text(dict_parts) == "Dict paragraph 1\nDict paragraph 2"


def test_content_to_wire_and_messages_to_wire() -> None:
    # Single string content
    msgs: list[dict[str, Any]] = [{"role": "user", "content": "hello"}]
    wire = _messages_to_wire(msgs)
    assert wire == [{"role": "user", "content": "hello"}]

    # Multi-modal parts
    msgs = [
        {
            "role": "user",
            "content": [
                TextPart(text="Check this image:"),
                ImagePart(url="https://example.com/diagram.png", detail="low"),
                FilePart(filename="test.txt", data="...", mime_type="text/plain"),
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_123",
            "content": "Tool output text",
        },
    ]
    wire = _messages_to_wire(msgs)
    assert len(wire) == 2
    assert wire[0]["role"] == "user"
    assert isinstance(wire[0]["content"], list)
    assert wire[0]["content"][0] == {"type": "text", "text": "Check this image:"}
    assert wire[0]["content"][1] == {
        "type": "image_url",
        "image_url": {"url": "https://example.com/diagram.png", "detail": "low"},
    }
    assert wire[0]["content"][2] == {"type": "text", "text": "[File: test.txt (text/plain)]"}

    # tool_call_id preserved
    assert wire[1]["role"] == "tool"
    assert wire[1]["tool_call_id"] == "call_123"
    assert wire[1]["content"] == "Tool output text"


def test_estimate_messages_multimodal() -> None:
    text_only = [{"role": "user", "content": "Hello world"}]
    base_tokens = estimate_messages(text_only)
    assert base_tokens > 0

    with_img_low = [
        {
            "role": "user",
            "content": [
                TextPart(text="Hello world"),
                ImagePart(url="https://example.com/img.png", detail="low"),
            ],
        }
    ]
    tokens_low = estimate_messages(with_img_low)
    # 3 text tokens + 85 image tokens
    assert tokens_low == 88

    with_img_high = [
        {
            "role": "user",
            "content": [
                TextPart(text="Hello world"),
                ImagePart(url="https://example.com/img.png", detail="high"),
            ],
        }
    ]
    tokens_high = estimate_messages(with_img_high)
    # 3 text tokens + 255 image tokens
    assert tokens_high == 258


def test_compressor_with_multimodal() -> None:
    msgs: list[dict[str, Any]] = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "prompt"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "t", "arguments": {}}],
        },
        {"role": "tool", "content": [ImagePart(url="data:image/png;base64,...")]},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "next"},
        {"role": "assistant", "content": "reply2"},
        {"role": "user", "content": "next2"},
        {"role": "assistant", "content": "final"},
    ]
    compressed = compress(msgs, budget=20)
    assert any("已压缩" in str(m.get("content")) for m in compressed)
