"""Generic OpenAI-compatible chat-completions client for standalone
agent runs (REPL / ``python -m agent.main``).

Responsibilities:
- Implement the agent-side LLMClient protocol (plus the optional streaming
  extension) against any OpenAI-compatible ``/chat/completions`` endpoint
  (OpenRouter, DeepSeek, Moonshot, Ollama, vLLM, ...)
- Translate the internal message shape (assistant ``tool_calls`` with dict
  arguments, ``tool`` result entries) to/from the wire format
- Fold provider errors into readable degraded replies instead of raising, so
  the ReAct loop treats them like any other turn (same semantics as the
  aggregate-run adapter)

This client is intentionally independent of packages/llm: the import-linter
rule forbids agent -> packages imports, and the OpenAI-compatible wire
protocol is an external standard, not an internal domain concern.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from agent.llm import LLMReply, StreamReply, ToolCall, ToolSpec, Usage

log = logging.getLogger("agent.llm_http")

_DEGRADED_PREFIX = "[LLM error]"
_DONE = "[DONE]"


@dataclass(frozen=True)
class HttpLlmConfig:
    """Connection settings for one OpenAI-compatible endpoint."""

    base_url: str  # e.g. https://api.deepseek.com/v1 (no trailing slash)
    api_key: str = ""
    model: str = ""
    timeout_s: float = 120.0
    temperature: float | None = None
    max_tokens: int | None = None


def _assistant_tool_calls_to_wire(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Internal assistant tool_calls (dict arguments) -> OpenAI wire shape."""
    out: list[dict[str, Any]] = []
    for c in calls:
        out.append(
            {
                "id": str(c.get("id", "")),
                "type": "function",
                "function": {
                    "name": str(c.get("name", "")),
                    "arguments": json.dumps(c.get("arguments") or {}, ensure_ascii=False),
                },
            }
        )
    return out


def _messages_to_wire(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Internal message list -> OpenAI chat-completions payload messages.

    Most entries pass through unchanged (system/user/content); only the
    assistant tool_calls shape and argument dicts need translation.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "assistant" and m.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    "content": str(m.get("content") or ""),
                    "tool_calls": _assistant_tool_calls_to_wire(m["tool_calls"]),
                }
            )
        else:
            out.append({"role": role, "content": str(m.get("content") or "")})
    return out


def _tools_to_wire(specs: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
    if not specs:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": s.name,
                "description": s.description,
                "parameters": s.schema or {"type": "object", "properties": {}},
            },
        }
        for s in specs
    ]


def _parse_tool_calls(raw: list[dict[str, Any]] | None) -> tuple[ToolCall, ...]:
    """Wire tool_calls -> internal ToolCall tuple; malformed argument JSON
    degrades to an empty argument dict so the loop can surface a tool error
    instead of crashing."""
    calls: list[ToolCall] = []
    for i, c in enumerate(raw or []):
        fn = c.get("function") or {}
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except (TypeError, ValueError):
            log.warning("malformed tool arguments from provider (call %s)", c.get("id"))
            args = {}
        if not isinstance(args, dict):
            args = {}
        calls.append(
            ToolCall(
                id=str(c.get("id") or f"call_{i}"),
                name=str(fn.get("name", "")),
                arguments=args,
            )
        )
    return tuple(calls)


def _error_text(status: int) -> str:
    """Map an HTTP failure to a short readable reason (the raw body is never
    echoed back into the conversation)."""
    if status in (401, 403):
        return f"{_DEGRADED_PREFIX} authentication failed (check the API key)"
    if status == 404:
        return f"{_DEGRADED_PREFIX} endpoint or model not found (check base_url / model)"
    if status == 429:
        return f"{_DEGRADED_PREFIX} rate limited by the provider"
    if status >= 500:
        return f"{_DEGRADED_PREFIX} provider server error"
    return f"{_DEGRADED_PREFIX} HTTP {status}"


def _is_context_overflow(status: int, body: str) -> bool:
    """Heuristic: providers phrase context-window rejections differently
    ("context length exceeded", "context_length_exceeded", "maximum context
    size"); they all arrive as HTTP 400."""
    if status != 400:
        return False
    lowered = body.lower()
    return "context" in lowered and (
        "length" in lowered or "overflow" in lowered or "window" in lowered
    )


class HttpLLM:
    """OpenAI-compatible client implementing complete + complete_stream.

    One shared AsyncClient per instance; errors are folded into degraded
    text replies (never raised) so callers need no provider-specific error
    handling.
    """

    def __init__(
        self, config: HttpLlmConfig, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._cfg = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {config.api_key}"} if config.api_key else {},
            timeout=config.timeout_s,
            transport=transport,  # injection point for tests (MockTransport)
        )

    @property
    def model(self) -> str:
        """Configured model name; the context-window resolver matches this
        against agent.context.model_profiles."""
        return self._cfg.model

    async def aclose(self) -> None:
        await self._client.aclose()

    def _payload(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._cfg.model,
            "messages": _messages_to_wire(messages),
            "stream": stream,
        }
        if stream:
            # Usage in the final SSE chunk; servers not supporting the option
            # are retried once without it (see complete_stream).
            body["stream_options"] = {"include_usage": True}
        wire_tools = _tools_to_wire(tools)
        if wire_tools:
            body["tools"] = wire_tools
        if self._cfg.temperature is not None:
            body["temperature"] = self._cfg.temperature
        if self._cfg.max_tokens is not None:
            body["max_tokens"] = self._cfg.max_tokens
        return body

    def _parse_reply(self, data: dict[str, Any]) -> LLMReply:
        choices = data.get("choices") or []
        msg = (choices[0].get("message") or {}) if choices else {}
        usage = data.get("usage") or {}
        return LLMReply(
            text=str(msg.get("content") or "") or None,
            tool_calls=_parse_tool_calls(msg.get("tool_calls")),
            usage=_parse_usage(usage),
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
    ) -> LLMReply:
        try:
            resp = await self._client.post(
                "/chat/completions", json=self._payload(messages, tools, stream=False)
            )
        except httpx.TimeoutException:
            return LLMReply(text=f"{_DEGRADED_PREFIX} request timed out", degraded=True)
        except httpx.HTTPError as exc:
            return LLMReply(
                text=f"{_DEGRADED_PREFIX} connection failed: {type(exc).__name__}", degraded=True
            )
        if resp.status_code != 200:
            return LLMReply(
                text=_error_text(resp.status_code),
                degraded=True,
                overflow=_is_context_overflow(resp.status_code, resp.text[:2000]),
            )
        try:
            return self._parse_reply(resp.json())
        except ValueError:
            return LLMReply(text=f"{_DEGRADED_PREFIX} malformed response body", degraded=True)

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
    ) -> AsyncIterator[StreamReply]:
        """Yield StreamReply events: text deltas then one final aggregate."""
        body = self._payload(messages, tools, stream=True)
        async for ev in self._stream_events(body):
            yield ev

    async def _stream_events(self, body: dict[str, Any]) -> AsyncIterator[StreamReply]:
        """Drive one SSE request: parse lines, aggregate tool-call fragments,
        emit deltas and a single final block.

        A 400 caused by stream_options (some compatible servers reject unknown
        options) is retried once without the option.
        """
        text_parts: list[str] = []
        calls_by_index: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        try:
            async with self._client.stream("POST", "/chat/completions", json=body) as resp:
                if resp.status_code == 400 and body.get("stream_options"):
                    # Server rejected the option: retry once without it
                    body = {k: v for k, v in body.items() if k != "stream_options"}
                    async for ev in self._stream_events(body):
                        yield ev
                    return
                if resp.status_code != 200:
                    await resp.aread()
                    yield StreamReply(
                        final=LLMReply(
                            text=_error_text(resp.status_code),
                            degraded=True,
                            overflow=_is_context_overflow(resp.status_code, resp.text[:2000]),
                        )
                    )
                    return
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_str = line[len("data:") :].strip()
                    if not data_str or data_str == _DONE:
                        continue
                    try:
                        chunk = json.loads(data_str)
                    except ValueError:
                        continue
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if delta.get("content"):
                            text_parts.append(delta["content"])
                            yield StreamReply(text_delta=delta["content"])
                        for frag in delta.get("tool_calls") or []:
                            self._merge_tool_fragment(calls_by_index, frag)
        except httpx.TimeoutException:
            yield StreamReply(
                final=LLMReply(
                    text=f"{_DEGRADED_PREFIX} request timed out",
                    degraded=True,
                )
            )
            return
        except httpx.HTTPError as exc:
            yield StreamReply(
                final=LLMReply(
                    text=f"{_DEGRADED_PREFIX} connection failed: {type(exc).__name__}",
                    degraded=True,
                )
            )
            return
        calls = tuple(
            ToolCall(
                id=str(calls_by_index[i].get("id") or f"call_{i}"),
                name=str(calls_by_index[i].get("name") or ""),
                arguments=_safe_json(calls_by_index[i].get("arguments", "")),
            )
            for i in sorted(calls_by_index)
        )
        text = "".join(text_parts)
        if calls:
            yield StreamReply(final=LLMReply(tool_calls=calls, usage=_parse_usage(usage)))
        else:
            yield StreamReply(final=LLMReply(text=text or None, usage=_parse_usage(usage)))

    @staticmethod
    def _merge_tool_fragment(acc: dict[int, dict[str, Any]], frag: dict[str, Any]) -> None:
        """Accumulate one streaming tool-call fragment by index: id/name arrive
        on the first fragment, arguments stream in pieces."""
        idx = int(frag.get("index", 0))
        slot = acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        if frag.get("id"):
            slot["id"] = frag["id"]
        fn = frag.get("function") or {}
        if fn.get("name"):
            slot["name"] += fn["name"]
        if fn.get("arguments"):
            slot["arguments"] += fn["arguments"]


def _parse_usage(usage: dict[str, Any]) -> Usage:
    return Usage(
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
    )


def _safe_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
