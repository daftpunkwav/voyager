"""LLM streaming client: SSE incremental parsing with complete's
error classification.

Responsibilities:
- Parse SSE line-by-line per wire format (chat = OpenAI-compatible,
  anthropic = Messages)
- Aggregate deltas into text chunks plus a final aggregate chunk shaped like
  complete's return (text / tool_calls / usage / model)
- Classify errors like complete: pre-first-packet errors keep retryable
  semantics; mid-stream errors are never retried automatically

client.py handles one-shot requests; this module only does streaming:
line-by-line SSE parsing and incremental aggregation per wire format
(chat = OpenAI-compatible, anthropic = Messages), producing dict chunks —
several `{"type": "text", "text": <delta>}` chunks and a final
`{"type": "final", "text", "tool_calls", "usage", "model"}` chunk (same shape
as the complete capability return, so adapters map them uniformly).

Error classification matches complete (_raise_typed_text): errors before the
first packet (status code/connection) keep retryable semantics; mid-stream
errors are never retried automatically (deltas already consumed) and network
errors are folded into a non-retriable TransientError. No silent degradation:
endpoints lacking streaming/usage support get an explicit error.

The chat format sends `stream_options: {"include_usage": true}` to request
usage figures; without it metering could only record 0 and quotas/usage pages
would be misleading. Anthropic usage arrives embedded in the message_start /
message_delta events.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from .client import (
    _TIMEOUT,
    TransientError,
    _anthropic_messages,
    _anthropic_tools,
    _chat_messages,
    _chat_tools,
    _parse_tool_calls,
    _raise_typed_text,
    _resolve_tool_messages,
    _split_system,
    reasoning_fields,
)


def _safe_arguments(raw: str) -> dict[str, Any]:
    """Lenient JSON parse of tool arguments (same policy as complete's
    _parse_tool_calls)."""
    if not raw:
        return {}
    try:
        args = json.loads(raw)
    except ValueError:
        return {}
    return args if isinstance(args, dict) else {}


async def complete_stream(
    provider: dict[str, Any],
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 4096,
    temperature: float = 0.7,
    tools: list[dict[str, Any]] | None = None,
    reasoning_effort: str = "",
) -> AsyncIterator[dict[str, Any]]:
    """Streaming completion: yields text deltas and a final aggregate chunk."""
    fmt = provider["api_format"]
    base = provider["base_url"].rstrip("/")
    messages = _resolve_tool_messages(messages)
    if fmt == "anthropic":
        system, rest = _split_system(messages)
        body: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system,
            "messages": _anthropic_messages(rest)
            or [
                {"role": "user", "content": "(no content, please continue)"},
            ],
            "stream": True,
        }
        if tools:
            body["tools"] = _anthropic_tools(tools)
        body.update(reasoning_fields(fmt, reasoning_effort, max_tokens=max_tokens))
        # Anthropic forbids temperature when extended thinking is enabled
        if "thinking" in body:
            body.pop("temperature", None)
        url = f"{base}/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        parser = _anthropic_sse
    else:
        body = {
            "model": model,
            "messages": _chat_messages(messages)
            or [
                {"role": "user", "content": "(no content, please continue)"},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            body["tools"] = _chat_tools(tools)
        body.update(reasoning_fields(fmt, reasoning_effort, max_tokens=max_tokens))
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}"}
        parser = _chat_sse

    in_body = False  # False = pre-first-packet (connection/status), True = body streaming
    try:
        async with (
            httpx.AsyncClient(timeout=_TIMEOUT) as client,
            client.stream("POST", url, headers=headers, json=body) as resp,
        ):
            if resp.status_code >= 400:
                text = (await resp.aread()).decode("utf-8", errors="replace")
                _raise_typed_text(resp.status_code, text)
            in_body = True
            async for chunk in parser(resp):
                yield chunk
    except httpx.TransportError as exc:
        # Mid-stream disconnect: deltas were already consumed and a retry
        # would duplicate output, so mark this non-retriable.
        raise TransientError(f"{type(exc).__name__}: {exc}", retriable=not in_body) from exc


async def _chat_sse(resp: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """OpenAI-compatible SSE: `data:` lines terminated by `[DONE]`;
    tool_calls reassembled from per-index fragments."""
    text_parts: list[str] = []
    frags: dict[int, dict[str, str]] = {}
    usage: dict[str, Any] = {}
    model = ""
    async for line in resp.aiter_lines():
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
        except ValueError:
            continue  # skip non-JSON lines (comments/keep-alives)
        model = str(obj.get("model") or model)
        if obj.get("usage"):
            usage = obj["usage"]
        for choice in obj.get("choices") or []:
            delta = choice.get("delta") or {}
            content = delta.get("content")
            if content:
                text_parts.append(str(content))
                yield {"type": "text", "text": str(content)}
            for tc in delta.get("tool_calls") or []:
                idx = int(tc.get("index") or 0)
                acc = frags.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                # Some endpoints resend the full id/name on every fragment:
                # overwrite the whole value (idempotent) instead of appending;
                # arguments are true fragments and must accumulate.
                if tc.get("id"):
                    acc["id"] = str(tc["id"])
                fn = tc.get("function") or {}
                if fn.get("name"):
                    acc["name"] = str(fn["name"])
                if fn.get("arguments"):
                    acc["arguments"] += str(fn["arguments"])
    tool_calls = _parse_tool_calls(
        [
            {"id": a["id"], "function": {"name": a["name"], "arguments": a["arguments"]}}
            for _, a in sorted(frags.items())
        ]
    )
    yield {
        "type": "final",
        "text": "".join(text_parts),
        "tool_calls": [dict(t) for t in tool_calls],
        "usage": {
            "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0),
            "cached_tokens": int(
                (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            ),
        },
        "model": model,
    }


async def _anthropic_sse(resp: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """Anthropic Messages SSE: dispatch on the data payload's `type` (event
    lines ignored); tool_use opens at content_block_start and its arguments
    are assembled from input_json_delta fragments."""
    text_parts: list[str] = []
    blocks: dict[int, dict[str, str]] = {}
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    model = ""
    async for line in resp.aiter_lines():
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if not data:
            continue
        try:
            obj = json.loads(data)
        except ValueError:
            continue
        kind = obj.get("type")
        if kind == "message_start":
            message = obj.get("message") or {}
            model = str(message.get("model") or model)
            start_usage = message.get("usage") or {}
            input_tokens = int(start_usage.get("input_tokens") or 0)
            cached_tokens = int(start_usage.get("cache_read_input_tokens") or 0)
        elif kind == "content_block_start":
            block = obj.get("content_block") or {}
            if block.get("type") == "tool_use":
                blocks[int(obj.get("index") or 0)] = {
                    "id": str(block.get("id") or ""),
                    "name": str(block.get("name") or ""),
                    "json": "",
                }
        elif kind == "content_block_delta":
            delta = obj.get("delta") or {}
            if delta.get("type") == "text_delta" and delta.get("text"):
                text_parts.append(str(delta["text"]))
                yield {"type": "text", "text": str(delta["text"])}
            elif delta.get("type") == "input_json_delta" and delta.get("partial_json"):
                idx = int(obj.get("index") or 0)
                if idx in blocks:
                    blocks[idx]["json"] += str(delta["partial_json"])
        elif kind == "message_delta":
            output_tokens = int((obj.get("usage") or {}).get("output_tokens") or output_tokens)
    tool_calls = tuple(
        {"id": b["id"], "name": b["name"], "arguments": _safe_arguments(b["json"])}
        for _, b in sorted(blocks.items())
    )
    yield {
        "type": "final",
        "text": "".join(text_parts),
        "tool_calls": [dict(t) for t in tool_calls],
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
        },
        "model": model,
    }


__all__ = ["complete_stream"]
