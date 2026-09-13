"""LLM client protocol and the fake LLM used for tests.

Real provider integrations live in packages/llm; this module defines the
protocols only. FakeLLM serves deterministic tests and the no-key
degradation path.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    #: Prompt tokens served from the provider's prefix cache (a subset of
    #: input_tokens); 0 when the provider reports nothing - callers must
    #: treat "never saw a warm round" separately from "cache broke"
    cached_tokens: int = 0


@dataclass(frozen=True)
class LLMReply:
    """One LLM response: either final text or a set of tool calls.

    degraded marks the reply as harness degradation text (quota exceeded etc.)
    rather than model-generated - callers distinguish "real reply" from
    "placeholder sentence" via the flag instead of guessing from text content.
    overflow marks a context-window overflow: the transcript exceeded the
    model's context and the call was refused; the ReAct loop reacts by
    compacting harder and retrying once instead of surfacing the failure.
    """

    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)
    degraded: bool = False
    overflow: bool = False

    @property
    def final(self) -> bool:
        return not self.tool_calls


@dataclass(frozen=True)
class StreamReply:
    """Streaming event: either a text delta chunk or the final aggregate block,
    never both.

    final has the same shape as complete's return (one uniform outlet); an
    aggregated stream ends with a single final block.
    """

    text_delta: str = ""
    final: LLMReply | None = None


class LLMClient(Protocol):
    async def complete(
        self, messages: list[dict[str, Any]], tools: list[ToolSpec] | None = None
    ) -> LLMReply: ...


class StreamingLLClient(Protocol):
    """Optional streaming extension: implementors additionally provide
    complete_stream.

    Not a closed protocol: LLMClient implementors may skip it; callers probe
    with callable(getattr(llm, "complete_stream", None)) and fall back to
    non-streaming complete when missing - not a silent feature downgrade but
    protocol tiering: streaming is an incremental capability.
    """

    def complete_stream(
        self, messages: list[dict[str, Any]], tools: list[ToolSpec] | None = None
    ) -> AsyncIterator[StreamReply]: ...


ScriptFn = Callable[[list[dict[str, Any]], list[ToolSpec] | None], LLMReply | Awaitable[LLMReply]]


class FakeLLM:
    """Scripted fake LLM: pops scripted replies in order; returns the default
    text when exhausted; can also generate dynamically via a function.

    dynamic accepts sync or async functions (async can simulate latency /
    timing scenarios)."""

    def __init__(
        self,
        script: list[LLMReply] | None = None,
        *,
        default: str = "Got it.",
        dynamic: ScriptFn | None = None,
    ) -> None:
        self._script = list(script or [])
        self._default = default
        self._dynamic = dynamic
        self.calls: list[dict[str, Any]] = []

    async def complete(
        self, messages: list[dict[str, Any]], tools: list[ToolSpec] | None = None
    ) -> LLMReply:
        self.calls.append({"messages": messages, "tools": tools})
        if self._dynamic is not None:
            out = self._dynamic(messages, tools)
            if isinstance(out, LLMReply):
                return out
            return await out
        if self._script:
            return self._script.pop(0)
        return LLMReply(text=self._default)
