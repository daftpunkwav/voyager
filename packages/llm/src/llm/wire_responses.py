"""OpenAI Responses wire format (``POST {base}/responses``).

Third wire format alongside ``chat`` (OpenAI Chat Completions) and
``anthropic`` (Anthropic Messages). Reasoning models on this endpoint return
thinking as a separate ``reasoning`` output item (summary text), so the
reasoning/answer channels are structural here — no inline ``<think>``
splitting is needed.

The subset of the protocol the agent needs:

- system messages -> ``instructions`` (joined, same policy as chat's
  ``_split_system``)
- user / assistant text -> input items with typed content parts
  (``input_text`` / ``output_text``)
- assistant ``tool_calls`` -> ``function_call`` items (call_id/name/arguments
  serialized to a JSON string)
- role ``tool`` results -> ``function_call_output`` items keyed by ``call_id``
- tools -> flat ``{"type": "function", name, description, parameters}``
  (Responses shape; Chat Completions nests them under ``function``)
- reasoning effort -> ``reasoning: {"effort": ...}``; max_tokens maps to
  ``max_output_tokens``
- non-stream response -> the ``output`` array of typed items (+ ``usage``)
- stream -> typed delta events; the final aggregate is parsed from the full
  output inside the ``response.completed`` event, which is more reliable than
  re-accumulating deltas and carries the usage figures
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


def responses_input(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Paired history (post ``_resolve_tool_messages``) -> ``(instructions,
    input items)``."""
    instructions = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            continue
        if role == "assistant":
            text = str(m.get("content") or "")
            if text:
                out.append(
                    {"role": "assistant", "content": [{"type": "output_text", "text": text}]}
                )
            for tc in m.get("tool_calls") or ():
                out.append(
                    {
                        "type": "function_call",
                        "call_id": str((tc or {}).get("id") or ""),
                        "name": str((tc or {}).get("name") or ""),
                        "arguments": json.dumps(
                            (tc or {}).get("arguments") or {}, ensure_ascii=False
                        ),
                    }
                )
        elif role == "tool":
            out.append(
                {
                    "type": "function_call_output",
                    "call_id": str(m.get("tool_call_id") or ""),
                    "output": str(m.get("content") or ""),
                }
            )
        else:  # user (and any unknown role) rides the user channel
            out.append(
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": str(m.get("content") or "")}],
                }
            )
    return instructions, out


def responses_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Tool specs -> Responses' flat function-tool shape."""
    return [
        {
            "type": "function",
            "name": t["name"],
            "description": t.get("description", ""),
            "parameters": t.get("schema") or {"type": "object"},
        }
        for t in tools
    ]


def parse_response_output(data: dict[str, Any]) -> dict[str, Any]:
    """One full response object -> the aggregate shape shared by the complete
    result and the stream's final chunk (text / reasoning / tool_calls /
    usage / model)."""
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "message":
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") == "output_text":
                    text_parts.append(str(part.get("text") or ""))
        elif kind == "reasoning":
            # OpenAI exposes summary text; some compatible endpoints attach a
            # raw content array instead. Both ride the reasoning channel.
            for part in item.get("summary") or []:
                if isinstance(part, dict) and part.get("type") == "summary_text":
                    reasoning_parts.append(str(part.get("text") or ""))
            for part in item.get("content") or []:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    reasoning_parts.append(part["text"])
        elif kind == "function_call":
            raw_args = item.get("arguments")
            if isinstance(raw_args, dict):
                args = raw_args
            else:
                try:
                    args = json.loads(str(raw_args or "{}"))
                except ValueError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
            tool_calls.append(
                {
                    "id": str(item.get("call_id") or item.get("id") or ""),
                    "name": str(item.get("name") or ""),
                    "arguments": args,
                }
            )
    usage = data.get("usage") or {}
    details = usage.get("input_tokens_details") or {}
    return {
        "text": "".join(text_parts),
        "reasoning": "".join(reasoning_parts),
        "tool_calls": tool_calls,
        "usage": {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "cached_tokens": int(details.get("cached_tokens") or 0),
        },
        "model": str(data.get("model") or ""),
    }


async def responses_sse(resp: httpx.Response) -> AsyncIterator[dict[str, Any]]:
    """Responses SSE: dispatch on the data payload's ``type``; text and
    reasoning summary stream as deltas, the final aggregate comes from a
    terminal event — ``response.completed`` and ``response.incomplete``
    (truncation at max_output_tokens; the same parser handles both, keeping
    any tool calls that made it into the output) — falling back to
    accumulated deltas if no terminal event arrives. ``response.failed``
    raises ProviderError so the error rides the existing degraded-reply
    path instead of being swallowed."""
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    final: dict[str, Any] | None = None
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
        if kind == "response.output_text.delta":
            text = str(obj.get("delta") or "")
            if text:
                text_parts.append(text)
                yield {"type": "text", "text": text}
        elif kind == "response.reasoning_summary_text.delta":
            text = str(obj.get("delta") or "")
            if text:
                reasoning_parts.append(text)
                yield {"type": "reasoning", "text": text}
        elif kind in ("response.completed", "response.incomplete"):
            final = parse_response_output(obj.get("response") or {})
        elif kind == "response.failed":
            # Model-level failure after HTTP 200 (content policy, internal
            # error, ...). Raising here propagates through the capability's
            # ProviderError -> ServiceError mapping into the agent's normal
            # degraded-reply path; delayed import breaks the client module
            # cycle (client imports this module for the complete path).
            from .client import ProviderError

            error = (obj.get("response") or {}).get("error") or {}
            message = str(error.get("message") if isinstance(error, dict) else error)
            raise ProviderError(f"responses stream failed: {message}", status=200)
    if final is None:
        final = {
            "text": "".join(text_parts),
            "reasoning": "".join(reasoning_parts),
            "tool_calls": [],
            "usage": {},
            "model": "",
        }
    yield {"type": "final", **final}


__all__ = [
    "parse_response_output",
    "responses_input",
    "responses_sse",
    "responses_tools",
]
