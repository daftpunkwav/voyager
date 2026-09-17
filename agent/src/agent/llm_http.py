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

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from agent.llm import (
    FilePart,
    ImagePart,
    LLMReply,
    StreamReply,
    TextPart,
    ToolCall,
    ToolSpec,
    Usage,
    content_to_text,
)

log = logging.getLogger("agent.llm_http")

_DEGRADED_PREFIX = "[LLM error]"
_DONE = "[DONE]"

#: Transient retry parameters: bounded exponential backoff for 5xx / network
#: blips / 429, mirroring the aggregate client's policy in packages/llm.
#: Module-level constants so tests can zero them out. Retry-After is capped
#: at 5s to avoid stalling agent loops.
_RETRY_ATTEMPTS = 2
_RETRY_BACKOFF = 0.5
_RETRY_AFTER_CAP = 5.0

#: No retry once the connection is established: the request may already have
#: been accepted by the server, so retrying only stacks up waiting time.
_NO_RETRY_NET = (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_TOOL_OPEN = "<tool_call>"
_TOOL_CLOSE = "</tool_call>"


def _partial_tag_len(buf: str, tags: tuple[str, ...]) -> int:
    """Length of the longest suffix of buf that is a proper prefix of any tag."""
    best = 0
    for tag in tags:
        for k in range(min(len(buf), len(tag) - 1), best, -1):
            if buf.endswith(tag[:k]):
                best = k
                break
    return best


class _InlineTagSplitter:
    """Splits inline ``<think>...</think>`` reasoning and ``<tool_call>``
    blocks out of content deltas (MiniMax-style endpoints inline both in
    content instead of their protocol fields). Tags may arrive split across
    chunks, hence the carry-tail state machine. Same semantics as
    packages/llm's inline_split.InlineTagSplitter (duplicated: agent ->
    packages imports are forbidden by the import-linter contract)."""

    def __init__(self) -> None:
        self._mode = "text"  # text | think | tool
        self._tail = ""
        self._blocks: list[str] = []
        self._block_acc: list[str] = []

    @property
    def tool_blocks(self) -> list[str]:
        """Captured ``<tool_call>`` block bodies (verbatim, tags removed)."""
        return self._blocks

    def feed(self, text: str) -> tuple[str, str]:
        """Feed one content delta; returns ``(answer_delta, reasoning_delta)``."""
        buf = self._tail + text
        self._tail = ""
        answer: list[str] = []
        reasoning: list[str] = []
        while True:
            if self._mode == "think":
                end = buf.find(_THINK_CLOSE)
                if end >= 0:
                    reasoning.append(buf[:end])
                    buf = buf[end + len(_THINK_CLOSE) :]
                    self._mode = "text"
                    continue
                keep = _partial_tag_len(buf, (_THINK_CLOSE,))
                reasoning.append(buf[: len(buf) - keep])
                self._tail = buf[len(buf) - keep :]
                return "".join(answer), "".join(reasoning)
            if self._mode == "tool":
                end = buf.find(_TOOL_CLOSE)
                if end >= 0:
                    self._block_acc.append(buf[:end])
                    buf = buf[end + len(_TOOL_CLOSE) :]
                    self._blocks.append("".join(self._block_acc))
                    self._block_acc = []
                    self._mode = "text"
                    continue
                keep = _partial_tag_len(buf, (_TOOL_CLOSE,))
                self._block_acc.append(buf[: len(buf) - keep])
                self._tail = buf[len(buf) - keep :]
                return "".join(answer), "".join(reasoning)
            start = buf.find(_THINK_OPEN)
            tool_start = buf.find(_TOOL_OPEN)
            if 0 <= start and (tool_start < 0 or start < tool_start):
                answer.append(buf[:start])
                buf = buf[start + len(_THINK_OPEN) :]
                self._mode = "think"
                continue
            if 0 <= tool_start:
                answer.append(buf[:tool_start])
                buf = buf[tool_start + len(_TOOL_OPEN) :]
                self._mode = "tool"
                continue
            keep = _partial_tag_len(buf, (_THINK_OPEN, _TOOL_OPEN))
            answer.append(buf[: len(buf) - keep])
            self._tail = buf[len(buf) - keep :]
            return "".join(answer), "".join(reasoning)

    def flush(self) -> tuple[str, str]:
        """Drain the carry tail at end of stream; call once before aggregating."""
        text, self._tail = self._tail, ""
        if not text and not self._block_acc:
            if self._mode == "tool":
                # Empty unclosed block: nothing to capture either way.
                self._mode = "text"
            return "", ""
        if self._mode == "think":
            return "", text
        if self._mode == "tool":
            # Unclosed tool block: capture what arrived so the caller can
            # decide (convert or drop); it never reaches the answer text.
            self._blocks.append("".join(self._block_acc) + text)
            self._block_acc = []
            self._mode = "text"
            return "", ""
        return text, ""


def _split_inline(text: str) -> tuple[str, str, list[str]]:
    """One-shot split of a whole content string; ``(answer, reasoning, tool_blocks)``."""
    splitter = _InlineTagSplitter()
    answer, reasoning = splitter.feed(text)
    tail_answer, tail_reasoning = splitter.flush()
    return answer + tail_answer, reasoning + tail_reasoning, splitter.tool_blocks


def _parse_tool_blocks(blocks: list[str]) -> tuple[ToolCall, ...]:
    """Tool-call block bodies -> ToolCall tuple (MiniMax/HF JSON shape);
    unparseable blocks (the garbled echo variant) are dropped with a
    warning — they never belong in the answer text. Ids are synthesized
    uniquely per call so result pairing stays unambiguous."""
    calls: list[ToolCall] = []
    n = 0
    for block in blocks:
        raw = block.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            log.warning("dropping unparseable inline tool_call block: %.80r", raw)
            continue
        entries = obj if isinstance(obj, list) else [obj]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            fn = entry.get("function") or {}
            name = str(entry.get("name") or fn.get("name") or "")
            if not name:
                continue
            args = entry.get("arguments", fn.get("arguments"))
            if isinstance(args, str):
                args = _safe_json(args)
            calls.append(
                ToolCall(
                    id=f"inline_{n}",
                    name=name,
                    arguments=args if isinstance(args, dict) else {},
                )
            )
            n += 1
    return tuple(calls)


def _retryable_status(status: int) -> bool:
    """Transient server-side failures worth another attempt: 429 rate
    limiting and 5xx provider errors. Other 4xx are request problems;
    retrying is pointless."""
    return status == 429 or status >= 500


def _retry_after_seconds(resp: httpx.Response) -> float:
    """Retry-After hint in seconds (0 when absent or unparseable)."""
    try:
        return max(0.0, float(resp.headers.get("Retry-After", "")))
    except ValueError:
        return 0.0


def _backoff_delay(attempt: int, resp: httpx.Response | None) -> float:
    """Exponential backoff for attempt n (0-based), raised to a client-hinted
    Retry-After when present (capped)."""
    delay = _RETRY_BACKOFF * (2**attempt)
    if resp is not None:
        delay = max(delay, min(_retry_after_seconds(resp), _RETRY_AFTER_CAP))
    return delay


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


def _content_to_wire(content: Any) -> str | list[dict[str, Any]]:
    """Convert content (str or list of ContentParts/dicts) to OpenAI content wire format."""
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        wire_parts: list[dict[str, Any]] = []
        for p in content:
            if isinstance(p, TextPart):
                wire_parts.append({"type": "text", "text": p.text})
            elif isinstance(p, ImagePart):
                wire_parts.append(
                    {"type": "image_url", "image_url": {"url": p.url, "detail": p.detail}}
                )
            elif isinstance(p, FilePart):
                # The wire has no file slot: only the descriptor travels, the
                # bulk bytes stay local (never serialized into the payload).
                wire_parts.append({"type": "text", "text": f"[File: {p.filename} ({p.mime_type})]"})
            elif isinstance(p, dict):
                ptype = p.get("type", "text")
                if ptype == "text":
                    wire_parts.append({"type": "text", "text": str(p.get("text", ""))})
                elif ptype == "image_url":
                    img_info = p.get("image_url")
                    if isinstance(img_info, dict):
                        wire_parts.append({"type": "image_url", "image_url": img_info})
                    elif isinstance(p.get("url"), str):
                        wire_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": p["url"], "detail": p.get("detail", "auto")},
                            }
                        )
                    else:
                        wire_parts.append({"type": "image_url", "image_url": {"url": str(img_info)}})
                else:
                    wire_parts.append(p)
            else:
                wire_parts.append({"type": "text", "text": str(p)})
        return wire_parts
    return str(content)


def _messages_to_wire(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Internal message list -> OpenAI chat-completions payload messages.

    Most entries pass through unchanged (system/user/content); assistant
    tool_calls shape and multi-modal content parts are translated.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        content = _content_to_wire(m.get("content"))
        if role == "assistant" and m.get("tool_calls"):
            out.append(
                {
                    "role": "assistant",
                    # Assistant content may be multi-modal list; wire keeps
                    # the list shape (OpenAI accepts string or part array).
                    "content": content,
                    "tool_calls": _assistant_tool_calls_to_wire(m["tool_calls"]),
                }
            )
        elif role == "tool":
            # Tool results must stay string on the wire: flatten parts.
            if not isinstance(content, str):
                content = content_to_text(m.get("content"))
            tool_msg: dict[str, Any] = {"role": "tool", "content": content}
            if "tool_call_id" in m:
                tool_msg["tool_call_id"] = str(m["tool_call_id"])
            out.append(tool_msg)
        else:
            out.append({"role": role, "content": content})
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
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._cfg.model,
            "messages": _messages_to_wire(messages),
            "stream": stream,
        }
        if response_format is not None:
            body["response_format"] = response_format
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

    def _parse_reply(
        self,
        data: dict[str, Any],
        response_format: dict[str, Any] | None = None,
    ) -> LLMReply:
        choices = data.get("choices") or []
        msg = (choices[0].get("message") or {}) if choices else {}
        usage = data.get("usage") or {}
        answer, inline_reasoning, tool_blocks = _split_inline(str(msg.get("content") or ""))
        calls = _parse_tool_calls(msg.get("tool_calls"))
        structured: Any = None
        if response_format is not None and answer:
            try:
                structured = json.loads(answer)
            except ValueError:
                log.warning("failed to parse structured response as JSON: %.80r", answer)
        # Inline <tool_call> markup converts only when the wire field stayed
        # empty (MiniMax echoes the markup alongside the parsed call — the
        # parsed field wins so the call runs exactly once).
        return LLMReply(
            text=answer or None,
            tool_calls=calls or _parse_tool_blocks(tool_blocks),
            usage=_parse_usage(usage),
            reasoning=str(msg.get("reasoning_content") or "") + inline_reasoning,
            structured=structured,
        )

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMReply:
        body = self._payload(messages, tools, stream=False, response_format=response_format)
        resp: httpx.Response | None = None
        net_error: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS + 1):
            resp, net_error = None, None
            try:
                resp = await self._client.post("/chat/completions", json=body)
                if not _retryable_status(resp.status_code):
                    break
            except _NO_RETRY_NET:
                # Connection was established: the request may already have
                # been accepted, so it is never retried.
                return LLMReply(text=f"{_DEGRADED_PREFIX} request timed out", degraded=True)
            except httpx.TransportError as exc:
                # Connect/DNS/timeout transport failures: transient.
                net_error = exc
            except httpx.HTTPError as exc:
                # Other HTTP-level request problems are not transient: fold
                # immediately instead of burning the retry budget.
                return LLMReply(
                    text=f"{_DEGRADED_PREFIX} connection failed: {type(exc).__name__}",
                    degraded=True,
                )
            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(_backoff_delay(attempt, resp))
        if net_error is not None:
            if isinstance(net_error, httpx.TimeoutException):
                return LLMReply(text=f"{_DEGRADED_PREFIX} request timed out", degraded=True)
            return LLMReply(
                text=f"{_DEGRADED_PREFIX} connection failed: {type(net_error).__name__}",
                degraded=True,
            )
        assert resp is not None  # the loop exits only with a response or a net error
        if resp.status_code != 200:
            return LLMReply(
                text=_error_text(resp.status_code),
                degraded=True,
                overflow=_is_context_overflow(resp.status_code, resp.text[:2000]),
            )
        try:
            return self._parse_reply(resp.json(), response_format=response_format)
        except ValueError:
            return LLMReply(text=f"{_DEGRADED_PREFIX} malformed response body", degraded=True)

    async def complete_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamReply]:
        """Yield StreamReply events: text deltas then one final aggregate."""
        body = self._payload(messages, tools, stream=True, response_format=response_format)
        async for ev in self._stream_events(body, response_format=response_format):
            yield ev

    async def _stream_events(
        self,
        body: dict[str, Any],
        response_format: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamReply]:
        """Drive one SSE request: parse lines, aggregate tool-call fragments,
        emit deltas and a single final block.

        The request-initiation phase retries bounded transient failures
        (429 / 5xx statuses, transport errors) - safe because nothing has
        been yielded yet; once deltas start flowing a dropped stream is
        terminal (a retry would duplicate text). A 400 caused by
        stream_options (some compatible servers reject unknown options) is
        retried once without the option.
        """
        emitted = False
        attempt = 0
        while True:
            # Per-attempt state: a retry re-streams the whole completion, so
            # anything an aborted attempt consumed must not leak into the next
            # one — a splitter left inside an open <think> would misroute the
            # retried stream's answer text onto the reasoning channel.
            text_parts: list[str] = []
            calls_by_index: dict[int, dict[str, Any]] = {}
            reasoning_parts: list[str] = []
            splitter = _InlineTagSplitter()
            usage: dict[str, Any] = {}
            retry_delay: float | None = None
            try:
                async with self._client.stream("POST", "/chat/completions", json=body) as resp:
                    if resp.status_code == 400 and body.get("stream_options"):
                        # Server rejected the option: retry once without it
                        body = {k: v for k, v in body.items() if k != "stream_options"}
                        continue
                    if resp.status_code != 200:
                        await resp.aread()
                        if _retryable_status(resp.status_code) and attempt < _RETRY_ATTEMPTS:
                            retry_delay = _backoff_delay(attempt, resp)
                            attempt += 1
                        else:
                            yield StreamReply(
                                final=LLMReply(
                                    text=_error_text(resp.status_code),
                                    degraded=True,
                                    overflow=_is_context_overflow(
                                        resp.status_code, resp.text[:2000]
                                    ),
                                )
                            )
                            return
                    else:
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
                                    answer, inline_reasoning = splitter.feed(delta["content"])
                                    if answer:
                                        text_parts.append(answer)
                                        emitted = True
                                        yield StreamReply(text_delta=answer)
                                    if inline_reasoning:
                                        # Inline <think> reasoning joins the
                                        # reasoning channel, never the answer.
                                        reasoning_parts.append(inline_reasoning)
                                        yield StreamReply(reasoning_delta=inline_reasoning)
                                if delta.get("reasoning_content"):
                                    # Own channel like the aggregate path: never
                                    # merged into the answer text stream.
                                    reasoning_parts.append(str(delta["reasoning_content"]))
                                    yield StreamReply(
                                        reasoning_delta=str(delta["reasoning_content"])
                                    )
                                for frag in delta.get("tool_calls") or []:
                                    self._merge_tool_fragment(calls_by_index, frag)
                        break
            except _NO_RETRY_NET:
                # Connection was established and the stream dropped: terminal,
                # a retry would duplicate whatever was already emitted.
                yield StreamReply(
                    final=LLMReply(
                        text=f"{_DEGRADED_PREFIX} request timed out",
                        degraded=True,
                    )
                )
                return
            except httpx.TimeoutException:
                # Connect-phase timeout: transient while the retry budget and
                # the no-emission guarantee both hold.
                if emitted or attempt >= _RETRY_ATTEMPTS:
                    yield StreamReply(
                        final=LLMReply(
                            text=f"{_DEGRADED_PREFIX} request timed out",
                            degraded=True,
                        )
                    )
                    return
                retry_delay = _backoff_delay(attempt, None)
                attempt += 1
            except httpx.TransportError as exc:
                # Connect/DNS/network transport failure: same transient
                # treatment while nothing has been emitted yet.
                if emitted or attempt >= _RETRY_ATTEMPTS:
                    yield StreamReply(
                        final=LLMReply(
                            text=f"{_DEGRADED_PREFIX} connection failed: {type(exc).__name__}",
                            degraded=True,
                        )
                    )
                    return
                retry_delay = _backoff_delay(attempt, None)
                attempt += 1
            except httpx.HTTPError as exc:
                # Other HTTP-level request problems are not transient: fold
                # immediately instead of burning the retry budget.
                yield StreamReply(
                    final=LLMReply(
                        text=f"{_DEGRADED_PREFIX} connection failed: {type(exc).__name__}",
                        degraded=True,
                    )
                )
                return
            assert retry_delay is not None  # a retry branch always sets the delay
            await asyncio.sleep(retry_delay)
        calls = tuple(
            ToolCall(
                id=str(calls_by_index[i].get("id") or f"call_{i}"),
                name=str(calls_by_index[i].get("name") or ""),
                arguments=_safe_json(calls_by_index[i].get("arguments", "")),
            )
            for i in sorted(calls_by_index)
        )
        tail_answer, tail_reasoning = splitter.flush()
        if tail_answer:
            text_parts.append(tail_answer)
        if tail_reasoning:
            reasoning_parts.append(tail_reasoning)
        if not calls:
            # Inline tool-call markup is the only carrier when the wire field
            # stayed empty; when both arrive the parsed field wins (no echo
            # double-execution). Read after flush so unclosed blocks count.
            calls = _parse_tool_blocks(splitter.tool_blocks)
        text = "".join(text_parts)
        reasoning = "".join(reasoning_parts)
        structured: Any = None
        if response_format is not None and text:
            try:
                structured = json.loads(text)
            except ValueError:
                log.warning("failed to parse structured streaming response as JSON: %.80r", text)
        if calls:
            yield StreamReply(
                final=LLMReply(
                    tool_calls=calls,
                    usage=_parse_usage(usage),
                    reasoning=reasoning,
                    structured=structured,
                )
            )
        else:
            yield StreamReply(
                final=LLMReply(
                    text=text or None,
                    usage=_parse_usage(usage),
                    reasoning=reasoning,
                    structured=structured,
                )
            )

    @staticmethod
    def _merge_tool_fragment(acc: dict[int, dict[str, Any]], frag: dict[str, Any]) -> None:
        """Accumulate one streaming tool-call fragment by index: arguments
        stream in pieces; some compat endpoints resend the full id/name on
        every fragment, so both are overwritten (idempotent), never appended."""
        idx = int(frag.get("index", 0))
        slot = acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        if frag.get("id"):
            slot["id"] = frag["id"]
        fn = frag.get("function") or {}
        if fn.get("name"):
            slot["name"] = str(fn["name"])
        if fn.get("arguments"):
            slot["arguments"] += fn["arguments"]


def _parse_usage(usage: dict[str, Any]) -> Usage:
    # Cached prompt tokens: OpenAI-compatible reports prompt_tokens_details.
    # cached_tokens; Anthropic-style gateways report cache_read_input_tokens.
    # A provider that reports neither stays 0 (never-warm, not broken).
    cached = int(
        (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        or usage.get("cache_read_input_tokens")
        or 0
    )
    return Usage(
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
        cached_tokens=cached,
    )


def _safe_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
