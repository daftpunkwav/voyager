"""Direct LLM HTTP client: no litellm dependency, plain httpx calls.

Responsibilities:
- Send requests in two wire formats: `chat` (OpenAI-compatible) and
  `anthropic` (Messages), including connection tests
- Normalize the neutral tools format and tool_calls, and encode the agent's
  neutral message history into each provider's native tool protocol
- Classify upstream errors (rate limit / auth / context overflow /
  transient) and retry retriable ones with bounded exponential backoff

Supports two API formats: `chat` (OpenAI-compatible) and `anthropic`
(Messages). Usage is written to the store by the caller after complete
succeeds (direct metering, not log parsing). The tools argument uses a
neutral format [{"name", "description", "schema"}] (aligned with agent
ToolSpec); tool_calls are normalized to [{"id", "name", "arguments": dict}]
with per-format conversion. Message history follows the agent's neutral
protocol: paired assistant.tool_calls / role:"tool" turns are encoded into
each provider's native tool protocol, and orphan tool results are downgraded
to user text (see _resolve_tool_messages).
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)

#: Transient retry parameters: exponential backoff for 5xx / network blips /
#: 429. Module-level constants so tests can zero them out. Retry-After is
#: capped at 5s to avoid stalling agent loops.
_RETRY_ATTEMPTS = 2
_RETRY_BACKOFF = 0.5
_RETRY_AFTER_CAP = 5.0

#: No retry once the connection is established: the request may already have
#: been accepted by the server, so retrying only stacks up waiting time.
_NO_RETRY_NET = (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)

#: Response-body markers for context overflow (providers word the error
#: differently in English and Chinese; this is a conservative intersection)
_OVERFLOW_MARKS = (
    "maximum context length",
    "context length",
    "context_length",
    "prompt is too long",
    "too many tokens",
    "input length",
    "上下文长度",
    "超出上下文",
)


class ProviderError(Exception):
    """Base class for upstream provider errors.

    The classification controls two things: whether the client layer retries
    with backoff (retriable) and which ServiceError suffix the capability
    layer maps the exception to. status is the HTTP status code (0 for
    network-level errors); retry_after is the wait time in seconds hinted by
    a 429 Retry-After header (0 = not provided).
    """

    def __init__(
        self,
        message: str,
        *,
        status: int = 0,
        retriable: bool = False,
        retry_after: float = 0.0,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retriable = retriable
        self.retry_after = retry_after


class RateLimitError(ProviderError):
    """429: rate limited / quota exhausted; retryable after backoff."""


class AuthError(ProviderError):
    """401/403: invalid key or missing permission; retrying is pointless."""


class ContextOverflowError(ProviderError):
    """Prompt exceeds the model's context window; retrying is pointless.
    Compress the prompt before trying again."""


class TransientError(ProviderError):
    """5xx / transient network failure; retryable by default (timeouts after
    the connection is established are marked non-retriable by the caller)."""

    def __init__(
        self,
        message: str,
        *,
        status: int = 0,
        retriable: bool = True,
        retry_after: float = 0.0,
    ) -> None:
        super().__init__(message, status=status, retriable=retriable, retry_after=retry_after)


@dataclass(frozen=True)
class CompleteResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0  # prompt tokens served from the provider's cache (subset of input)
    model: str = ""
    tool_calls: tuple[dict[str, Any], ...] = ()
    #: Model thinking surfaced separately from the answer text: Anthropic
    #: thinking blocks and OpenAI-style reasoning_content, concatenated.
    #: Never mixed into text, so callers can render or drop it independently.
    reasoning: str = ""
    #: Raw Anthropic thinking/redacted_thinking blocks, verbatim, for
    #: echo-back on later turns (extended thinking requires the exact blocks
    #: back when tool use continues the conversation). Empty for chat format.
    thinking_blocks: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class TestResult:
    ok: bool
    latency_ms: float = 0.0
    model: str = ""
    error: str = ""


def _split_system(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    rest = [m for m in messages if m.get("role") != "system"]
    return system, rest


def _resolve_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep paired history in the neutral tool protocol; downgrade orphan or
    broken turns to avoid endpoint 400s.

    Strict endpoints require every tool_call id declared by an assistant
    message to have a matching result appearing after it. History may still
    contain leftovers from old sessions, partial compressor deletion, or
    interrupted loops. Sending orphans verbatim is rejected by Anthropic-style
    endpoints (MiniMax compat layer, error 2013 "tool result's tool id not
    found") and by OpenAI endpoints — so orphans are rewritten as user text,
    and tool_calls without results are dropped from the outgoing copy (the
    caller's messages are not mutated).
    """
    seen_ids: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or ():
                tid = str((tc or {}).get("id") or "")
                if tid:
                    seen_ids.add(tid)
            out.append(m)
            continue
        if m.get("role") == "tool":
            tid = str(m.get("tool_call_id") or "")
            if tid and tid in seen_ids:
                out.append(m)
            else:
                name = str(m.get("name") or "tool")
                out.append(
                    {"role": "user", "content": f"[Tool {name} result]\n{m.get('content', '')}"}
                )
            continue
        out.append(m)

    have_results = {
        str(m.get("tool_call_id") or "")
        for m in out
        if m.get("role") == "tool" and m.get("tool_call_id")
    }
    cleaned: list[dict[str, Any]] = []
    for m in out:
        calls = m.get("tool_calls") if m.get("role") == "assistant" else None
        if not calls:
            cleaned.append(m)
            continue
        kept = [tc for tc in calls if str((tc or {}).get("id") or "") in have_results]
        if len(kept) == len(calls):
            cleaned.append(m)
            continue
        if not kept and not str(m.get("content") or ""):
            continue
        nm = {**m, "tool_calls": kept}
        if not kept:
            nm = {k: v for k, v in nm.items() if k != "tool_calls"}
        cleaned.append(nm)
    return cleaned


def _chat_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Paired history -> OpenAI wire format: assistant.tool_calls gain the
    type/function shape with arguments serialized to a JSON string.
    role:"tool" and tool_call_id are native OpenAI fields and pass through
    unchanged (orphans were already downgraded by _resolve_tool_messages)."""
    out: list[dict[str, Any]] = []
    for m in messages:
        tool_calls = m.get("tool_calls") if m.get("role") == "assistant" else None
        if not tool_calls:
            out.append(m)
            continue
        out.append(
            {
                **m,
                "tool_calls": [
                    {
                        "id": str(tc.get("id") or ""),
                        "type": "function",
                        "function": {
                            "name": str(tc.get("name") or ""),
                            "arguments": json.dumps(tc.get("arguments") or {}, ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ],
            }
        )
    return out


def _anthropic_messages(rest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Non-system history -> Anthropic wire format (content blocks, no longer
    collapsed into a plain string).

    - assistant: a text block (if any) plus tool_use blocks (id/name/input);
      drop entirely when both are empty (Anthropic rejects empty content —
      another source of MiniMax 2013 "messages must not be empty").
    - role:"tool": converted to a tool_result block inside a user message,
      with tool_use_id matching the originating tool_use (note: Anthropic's
      field name, not OpenAI's tool_call_id); consecutive results are merged
      into one user message — the Anthropic convention is several tool_result
      blocks in a single user message per assistant turn.
    - other messages: string content passes through unchanged.
    """
    out: list[dict[str, Any]] = []
    for m in rest:
        role = m.get("role")
        if role == "assistant":
            text = str(m.get("content") or "")
            blocks: list[dict[str, Any]] = []
            # Echo stored thinking blocks first and verbatim: with extended
            # thinking enabled the provider requires the exact blocks back
            # while tool use continues the conversation.
            blocks.extend(_echoable_thinking_blocks(m))
            if text:
                blocks.append({"type": "text", "text": text})
            for tc in m.get("tool_calls") or ():
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": str(tc.get("id") or ""),
                        "name": str(tc.get("name") or ""),
                        "input": tc.get("arguments") or {},
                    }
                )
            if blocks:
                out.append({"role": "assistant", "content": blocks})
            continue
        if role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": str(m.get("tool_call_id") or ""),
                "content": str(m.get("content") or ""),
            }
            prev = out[-1] if out else None
            if (
                prev is not None
                and prev.get("role") == "user"
                and isinstance(prev.get("content"), list)
                and prev["content"]
                and all(b.get("type") == "tool_result" for b in prev["content"])
            ):
                prev["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        out.append({"role": role, "content": str(m.get("content") or "")})
    return out


def _chat_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("schema") or {"type": "object"},
            },
        }
        for t in tools
    ]


def _anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("schema") or {"type": "object"},
        }
        for t in tools
    ]


def _parse_tool_calls(raw: list[dict[str, Any]] | None) -> tuple[dict[str, Any], ...]:
    """chat format: arguments is a JSON string; fall back to empty args on
    parse failure."""
    calls = []
    for tc in raw or []:
        fn = tc.get("function") or {}
        args = fn.get("arguments") or "{}"
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}
        calls.append(
            {
                "id": tc.get("id", ""),
                "name": fn.get("name", ""),
                "arguments": args if isinstance(args, dict) else {},
            }
        )
    return tuple(calls)


def _retry_after_seconds(resp: httpx.Response) -> float:
    raw = resp.headers.get("retry-after", "")
    try:
        return max(float(raw), 0.0)
    except ValueError:
        return 0.0


def _looks_overflow(body: str) -> bool:
    low = body.lower()
    return any(mark in low for mark in _OVERFLOW_MARKS)


def _raise_typed(resp: httpx.Response) -> None:
    """On non-2xx, classify by status code/body and raise the matching
    ProviderError subclass."""
    if resp.status_code >= 400:
        _raise_typed_text(resp.status_code, resp.text, retry_after=_retry_after_seconds(resp))


def _raise_typed_text(status: int, body: str, *, retry_after: float = 0.0) -> None:
    """Classify by status code and body text (streaming path reuses this
    after aread).

    The message keeps a body summary: the provider's real error reason
    (MiniMax 2013, quota/auth wording) is needed for user-facing diagnosis.
    """
    if status < 400:
        return
    summary = body[:200]
    msg = f"HTTP {status}: {summary}"
    if status == 429:
        raise RateLimitError(msg, status=status, retriable=True, retry_after=retry_after)
    if status in (401, 403):
        raise AuthError(msg, status=status)
    if status == 400 and _looks_overflow(summary):
        raise ContextOverflowError(msg, status=status)
    if status >= 500:
        raise TransientError(msg, status=status)
    raise ProviderError(msg, status=status)


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


async def _send_with_retry(
    attempt: Callable[[], Awaitable[httpx.Response]],
) -> httpx.Response:
    """Exponential backoff retry for transient errors: 5xx / network blips /
    429.

    Only retriable ProviderErrors are retried. Timeouts after the connection
    is established (ReadTimeout etc.) may mean the request was already
    accepted; those are marked non-retriable and fail on first occurrence.
    """
    for i in range(_RETRY_ATTEMPTS + 1):
        try:
            return await attempt()
        except ProviderError as exc:
            if not exc.retriable or i >= _RETRY_ATTEMPTS:
                raise
            delay = _RETRY_BACKOFF * (2**i)
            if exc.retry_after:
                delay = max(delay, min(exc.retry_after, _RETRY_AFTER_CAP))
            await _sleep(delay)
    raise AssertionError("unreachable: loop must either return or raise")  # pragma: no cover


async def _post(
    client: httpx.AsyncClient, url: str, *, headers: dict[str, str], body: dict[str, Any]
) -> httpx.Response:
    """Single POST: network-level errors normalized to TransientError; non-2xx
    classified and raised."""
    try:
        resp = await client.post(url, headers=headers, json=body)
    except _NO_RETRY_NET as exc:
        raise TransientError(f"{type(exc).__name__}: {exc}", retriable=False) from exc
    except httpx.TransportError as exc:  # transient connect/DNS/timeout: retryable
        raise TransientError(f"{type(exc).__name__}: {exc}") from exc
    _raise_typed(resp)
    return resp


#: Reasoning-effort names and their Anthropic thinking budgets (tokens).
#: OpenAI-compatible endpoints take the effort value verbatim as
#: reasoning_effort; unknown values degrade to unset.
REASONING_EFFORTS = {"low": 2048, "medium": 8192, "high": 16384}


def reasoning_fields(fmt: str, reasoning_effort: str, *, max_tokens: int) -> dict[str, Any]:
    """Extra request-body fields for the configured reasoning effort; empty
    when the effort is unset or unknown so nothing is injected by default.

    chat (OpenAI-compatible): reasoning_effort passes through verbatim.
    anthropic: a thinking block with a token budget; Anthropic requires
    max_tokens above the budget and no temperature, so max_tokens is raised
    and the caller must drop temperature when the returned dict has thinking.

    Extended thinking coexists with tool use (interleaved thinking): the
    thinking block rides alongside tools in the same request. The provider
    requires the returned thinking blocks back verbatim on following turns
    while tool use continues, so callers must persist
    CompleteResult.thinking_blocks into the transcript and re-emit them via
    _anthropic_messages (which echoes a stored "thinking_blocks" entry first
    in each assistant message).
    """
    if reasoning_effort not in REASONING_EFFORTS:
        return {}
    if fmt == "anthropic":
        budget = REASONING_EFFORTS[reasoning_effort]
        return {
            "thinking": {"type": "enabled", "budget_tokens": budget},
            "max_tokens": max(max_tokens, budget + 1024),
        }
    return {"reasoning_effort": reasoning_effort}


#: Content-block types echoed back verbatim for extended thinking.
_THINKING_BLOCK_TYPES = ("thinking", "redacted_thinking")


def _echoable_thinking_blocks(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Stored thinking blocks of one neutral assistant message, sanitized for
    the wire: only well-formed thinking/redacted_thinking dicts pass, so a
    poisoned history entry can never inject arbitrary content blocks."""
    stored = message.get("thinking_blocks") or ()
    if not isinstance(stored, (list, tuple)):
        return []
    out = []
    for block in stored:
        if (
            isinstance(block, dict)
            and block.get("type") in _THINKING_BLOCK_TYPES
            and (block.get("type") == "redacted_thinking" or isinstance(block.get("thinking"), str))
        ):
            out.append(dict(block))
    return out


async def complete(
    provider: dict[str, Any],
    *,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int = 4096,
    temperature: float = 0.7,
    tools: list[dict[str, Any]] | None = None,
    reasoning_effort: str = "",
) -> CompleteResult:
    fmt = provider["api_format"]
    base = provider["base_url"].rstrip("/")
    messages = _resolve_tool_messages(messages)
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        if fmt == "anthropic":
            system, rest = _split_system(messages)
            body: dict[str, Any] = {
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                # rest is empty (system only): never send an empty messages
                # array or MiniMax answers 2013
                "messages": _anthropic_messages(rest)
                or [
                    {"role": "user", "content": "(no content, please continue)"},
                ],
            }
            if tools:
                body["tools"] = _anthropic_tools(tools)
            body.update(reasoning_fields(fmt, reasoning_effort, max_tokens=max_tokens))
            # Anthropic forbids temperature when extended thinking is enabled.
            # Thinking and tool use coexist (interleaved thinking); the echo
            # of stored thinking blocks happens in _anthropic_messages.
            if "thinking" in body:
                body.pop("temperature", None)
            resp = await _send_with_retry(
                lambda: _post(
                    client,
                    f"{base}/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    body=body,
                )
            )
            data = resp.json()
            usage = data.get("usage") or {}
            blocks = data.get("content") or []
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            reasoning = "".join(
                str(b.get("thinking") or "") for b in blocks if b.get("type") == "thinking"
            )
            thinking_blocks = tuple(
                dict(b)
                for b in blocks
                if isinstance(b, dict) and b.get("type") in _THINKING_BLOCK_TYPES
            )
            tool_calls = tuple(
                {
                    "id": b.get("id", ""),
                    "name": b.get("name", ""),
                    "arguments": b.get("input") or {},
                }
                for b in blocks
                if b.get("type") == "tool_use"
            )
            return CompleteResult(
                text=text,
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                cached_tokens=int(usage.get("cache_read_input_tokens") or 0),
                model=data.get("model", model),
                tool_calls=tool_calls,
                reasoning=reasoning,
                thinking_blocks=thinking_blocks,
            )
        body = {
            "model": model,
            "messages": _chat_messages(messages)
            or [
                {"role": "user", "content": "(no content, please continue)"},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = _chat_tools(tools)
        body.update(reasoning_fields(fmt, reasoning_effort, max_tokens=max_tokens))
        resp = await _send_with_retry(
            lambda: _post(
                client,
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                body=body,
            )
        )
        data = resp.json()
        usage = data.get("usage") or {}
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        return CompleteResult(
            text=str(message.get("content") or ""),
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
            cached_tokens=int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0),
            model=data.get("model", model),
            tool_calls=_parse_tool_calls(message.get("tool_calls")),
            reasoning=str(message.get("reasoning_content") or ""),
        )


async def test_connection(provider: dict[str, Any], *, api_key: str, model: str) -> TestResult:
    """Connectivity test: send one minimal real request, report latency/error."""
    start = time.perf_counter()
    try:
        result = await complete(
            provider,
            api_key=api_key,
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
        )
    except ProviderError as exc:
        # complete already embedded the status code and body summary in the
        # message; reuse it to avoid "HTTP 400: HTTP 400:" duplication
        return TestResult(
            ok=False,
            latency_ms=(time.perf_counter() - start) * 1000,
            model=model,
            error=str(exc),
        )
    except Exception as exc:  # noqa: BLE001  # errors become a result, not a raise
        return TestResult(
            ok=False,
            latency_ms=(time.perf_counter() - start) * 1000,
            model=model,
            error=f"{type(exc).__name__}: {exc}",
        )
    return TestResult(
        ok=bool(result.text or result.model),
        latency_ms=(time.perf_counter() - start) * 1000,
        model=result.model or model,
    )
