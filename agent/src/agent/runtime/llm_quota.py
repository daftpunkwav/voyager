"""Daily LLM quota: the precheck wrapper (metered_llm) around any LLMClient
and the quota-exhausted reply detection.

Every completion is quota-prechecked, then recorded (ok or failed); when the
inner llm implements complete_stream the wrapper exposes the streaming
channel with the same precheck and one record per stream.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from agent.llm import LLMClient, LLMReply, StreamReply, Usage
from agent.runtime.meter import Meter, MeterRecord

log = logging.getLogger("agent.quota")


#: Degraded text for daily quota exhaustion: matches the ServiceLLM error presentation
#: (readable LLMReply text, no interruption of the agent loop); no exception is raised.
_QUOTA_EXCEEDED = "（今日 LLM token 配额已用完:明天自动恢复,或在设置里调高/关闭日配额。）"


def is_quota_exceeded_reply(reply: LLMReply | str | None) -> bool:
    """Detect whether a reply is the quota-exhausted degraded message.

    The LLMReply.degraded flag is checked first (set by metered_llm on degradation, so the
    check is unambiguous -- identical wording inside a normal model reply is no longer
    misjudged). The legacy bare-text path falls back to the two key substrings of the
    degraded text, decoupled from the exact _QUOTA_EXCEEDED wording: changing the copy does
    not affect detection.
    """
    if isinstance(reply, LLMReply):
        return reply.degraded
    if isinstance(reply, str):
        return "配额" in reply and "用完" in reply
    return False


def metered_llm(
    llm: LLMClient,
    meter: Meter,
    *,
    model: str = "default",
    quota_fn: Callable[[], int] | None = None,
) -> LLMClient:
    """Wrap an LLM client: check the daily token quota before each complete, then record
    duration and tokens.

    quota_fn hot-reads the daily token limit (e.g. agent.resource.daily_tokens) on every
    complete call -- quota changes from the settings page apply from the next sentence; None
    or 0 means unlimited. When over quota, no real call is made and nothing is metered; the
    degraded text is returned directly.

    When the inner llm implements complete_stream (optional streaming extension), the wrapper
    exposes the streaming channel too: the same quota precheck applies, and metering records
    once at stream end using final.usage (aligned with one record per complete call).
    """

    def _quota_degraded() -> LLMReply | None:
        if quota_fn is None:
            return None
        try:
            limit = int(quota_fn())
        except (TypeError, ValueError):
            log.warning("invalid daily token quota setting, treating as unlimited: %r", quota_fn())
            limit = 0  # a dirty value counts as unlimited (availability first): warn and allow
        if limit > 0 and meter.tokens_used_today() >= limit:
            return LLMReply(text=_QUOTA_EXCEEDED, degraded=True)
        return None

    class _MeteredBase:
        async def complete(self, messages, tools=None) -> LLMReply:
            degraded = _quota_degraded()
            if degraded is not None:
                return degraded
            start = time.perf_counter()
            reply: LLMReply | None = None
            ok = False  # success is recorded only after a full return; exceptions/cancel fail
            try:
                reply = await llm.complete(messages, tools)
                ok = True
                return reply
            finally:
                ms = (time.perf_counter() - start) * 1000
                usage = reply.usage if reply is not None else Usage()
                meter.record(
                    MeterRecord(
                        kind="llm",
                        name=model,
                        ms=ms,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        ok=ok,
                    )
                )

    class _MeteredStreaming(_MeteredBase):
        def complete_stream(self, messages, tools=None):
            return self._stream(messages, tools)

        async def _stream(self, messages, tools=None):
            degraded = _quota_degraded()
            if degraded is not None:
                yield StreamReply(final=degraded)
                return
            start = time.perf_counter()
            final: LLMReply | None = None
            ok = False  # success is recorded only after the stream ends; mid-stream errors fail
            try:
                async for ev in llm.complete_stream(messages, tools):
                    if ev.final is not None:
                        final = ev.final
                    yield ev
                if final is None:
                    # out-of-contract case (stream without a final block): synthesize an
                    # empty final so consumers do not hang
                    final = LLMReply()
                    yield StreamReply(final=final)
                ok = True
            finally:
                ms = (time.perf_counter() - start) * 1000
                usage = final.usage if final is not None else Usage()
                meter.record(
                    MeterRecord(
                        kind="llm",
                        name=model,
                        ms=ms,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        ok=ok,
                    )
                )

    has_stream = callable(getattr(llm, "complete_stream", None))
    return _MeteredStreaming() if has_stream else _MeteredBase()


__all__ = ["is_quota_exceeded_reply", "metered_llm"]
