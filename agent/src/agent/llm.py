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
class TextPart:
    text: str
    type: str = "text"


@dataclass(frozen=True)
class ImagePart:
    url: str
    detail: str = "auto"
    type: str = "image_url"


@dataclass(frozen=True)
class FilePart:
    filename: str
    data: str
    mime_type: str = "application/octet-stream"
    type: str = "file"


ContentPart = TextPart | ImagePart | FilePart
MessageContent = str | list[ContentPart | dict[str, Any]]


def content_to_text(content: Any) -> str:
    """Extract plain text representation from str or multi-modal content parts."""
    if not content:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, TextPart):
                parts.append(part.text)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, (ImagePart, FilePart)):
                continue
            else:
                parts.append(str(part))
        return "\n".join(parts) if parts else ""
    return str(content)


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
    reasoning carries model thinking separately from the answer text
    (Anthropic thinking blocks / OpenAI-style reasoning_content); it is
    rendered into the trajectory thinking block, never into the reply text.
    thinking_blocks are the raw Anthropic thinking/redacted blocks for
    verbatim echo-back while tool use continues the conversation.
    """

    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)
    degraded: bool = False
    overflow: bool = False
    # Resolved model name reported by the adapter (empty when unknown); the
    # round step trail records it so model switches land in the trajectory.
    model: str = ""
    reasoning: str = ""
    thinking_blocks: tuple[dict[str, Any], ...] = ()
    #: Parsed or validated structured data when schema/response_format was requested
    structured: Any = None
    #: The exact provider request body as sent on the wire (stream flags,
    #: temperature, thinking fields, tools). Attached by the llm domain's
    # complete_stream final chunk; None when the client did not report it
    # (non-streaming path, FakeLLM, older adapters). Feeds the raw round log.
    request_body: dict[str, Any] | None = None
    #: Provider response metadata, normalized across wire formats:
    #: finish_reason (truncation visibility!), request_id, service_tier,
    #: stop_sequence, created. Empty when not reported. A "length" /
    #: "max_tokens" / "max_output_tokens" finish_reason means the answer was
    #: cut off — consumers must surface that instead of treating the text as
    #: complete.
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def truncated(self) -> bool:
        """The provider ended this response because the output cap ran out
        (chat "length" / anthropic "max_tokens" / responses "incomplete"),
        not because the model finished."""
        return str(self.meta.get("finish_reason") or "") in (
            "length",
            "max_tokens",
            "max_output_tokens",
        )

    @property
    def final(self) -> bool:
        return not self.tool_calls


@dataclass(frozen=True)
class StreamReply:
    """Streaming event: either a text delta chunk or the final aggregate block,
    never both.

    final has the same shape as complete's return (one uniform outlet); an
    aggregated stream ends with a single final block. reasoning_delta carries
    live model thinking on its own channel; consumers must not merge it into
    the answer text (the final aggregate repeats it in LLMReply.reasoning).
    """

    text_delta: str = ""
    final: LLMReply | None = None
    reasoning_delta: str = ""


class LLMClient(Protocol):
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        response_format: dict[str, Any] | None = None,
        max_tokens: int | None = None,
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
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[StreamReply]: ...


ScriptFn = Callable[..., LLMReply | Awaitable[LLMReply]]


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
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec] | None = None,
        response_format: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> LLMReply:
        call_record: dict[str, Any] = {"messages": messages, "tools": tools}
        if response_format is not None:
            call_record["response_format"] = response_format
        if max_tokens is not None:
            call_record["max_tokens"] = max_tokens
        self.calls.append(call_record)
        if self._dynamic is not None:
            try:
                out = self._dynamic(messages, tools, response_format=response_format)
            except TypeError:
                out = self._dynamic(messages, tools)
            if isinstance(out, LLMReply):
                return out
            return await out
        if self._script:
            return self._script.pop(0)
        return LLMReply(text=self._default)
