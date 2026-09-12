"""LLM-driven transcript restructuring: the model sees its own
transcript as numbered, pair-shaped segments and decides what to keep, what to
fold into a dense summary, and what to drop outright.

Division of labor:
- The LLM decides (the plan): this is the primary context-management
  intelligence, per the "LLM knows its own window" principle.
- The harness enforces invariants: segmentation is pair-shaped so
  assistant(tool_calls)/tool groups can never split, leading system entries are
  forced keeps, the freshest exchange is forced kept, and a plan that fails
  validation (or a planner that fails to answer) falls back to deterministic
  compression - a failed compaction must never crash or corrupt the loop.

The summary is injected as a user message tagged with SUMMARY_MARK at the
position of the first summarized segment; instance-level write-back of that
mark into cross-turn history keeps long tasks from re-condensing the same
span every turn.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent.context.compressor import compress
from agent.context.tokenizer import estimate_messages
from agent.llm import LLMClient

log = logging.getLogger("agent.context.editor")

#: Marker prefix for the summary message (detected at turn end to persist the
#: condensed transcript across turns)
SUMMARY_MARK = "[历史压缩]"


def iter_segments(messages: list[dict[str, Any]]) -> list[tuple[int, int]]:
    """Split a transcript into half-open [begin, end) segments.

    Segment shapes (same pairing accounting as compressor._prune_span):
    - a leading (or any) system message is its own segment;
    - an assistant message with tool_calls plus its contiguous tool results is
      one atomic segment;
    - every other message (user, plain assistant, orphan tool) is its own
      segment.

    Because segments are pair-shaped, any subset of segments preserves the
    "every call has a result" shape the endpoint requires.
    """
    segments: list[tuple[int, int]] = []
    i = 0
    n = len(messages)
    while i < n:
        role = messages[i].get("role")
        if role == "assistant" and messages[i].get("tool_calls"):
            end = i + 1
            while end < n and messages[end].get("role") == "tool":
                end += 1
            segments.append((i, end))
            i = end
        else:
            segments.append((i, i + 1))
            i += 1
    return segments


def render_segment_map(segments: list[tuple[int, int]]) -> str:
    """One line per segment: its message-index range. The planner reads the
    verbatim transcript above and this map; nothing else is re-rendered."""
    return "\n".join(
        f"[段{idx}] 消息 {begin}-{end - 1}" for idx, (begin, end) in enumerate(segments)
    )


_PLAN_PROMPT = (
    "【上下文编辑任务】当前对话窗口紧张。上方就是对话转录原文(未做任何改写)。"
    "分段对照见本条消息末尾。请决定如何重组以腾出空间,只输出一个 JSON 对象,不要输出其他文字:\n"
    '{"keep": [段号], "summarize": [段号], "drop": [段号], "summary": "<摘要正文>"}\n'
    "规则:\n"
    "1) keep 的段原样保留;summarize 的段合并进 summary;drop 的段直接丢弃;"
    "未提到的段默认保留。\n"
    "2) summary 是一段「密集工作状态」(不超过400字),依次覆盖:当前任务目标;"
    "已完成的关键步骤与结论;重要决策/数据/路径等关键值(原样保留);未完成事项与下一步。\n"
    "3) 最后一段必须出现在 keep 中;最近的用户要求、未完成承诺、关键事实优先原样保留。\n"
    "4) 没有信息量的寒暄、重复内容、已被取代的陈旧探索可以 drop。\n"
    "5) summarize 非空时 summary 必须是摘要正文本身。\n\n"
    "分段对照:\n"
)


def parse_plan(text: str) -> dict[str, Any] | None:
    """Parse the planner reply as a plan dict; tolerate a fenced block.
    None when the reply is not a JSON object."""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.removeprefix("json")
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _int_list(value: Any) -> list[int] | None:
    """Strictly a list of ints (bool excluded); None otherwise."""
    if not isinstance(value, list):
        return None
    out: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            return None
        out.append(item)
    return out


def validate_plan(
    plan: dict[str, Any], segments: list[tuple[int, int]], messages: list[dict[str, Any]]
) -> bool:
    """Harness-side invariant check for a plan; an invalid plan is rejected
    whole (never partially applied) and falls back to deterministic
    compression.

    - keep/summarize/drop are int lists with in-range, pairwise-disjoint ids;
    - segments made only of system messages are forced keeps;
    - the last segment is forced kept (protects the freshest exchange);
    - summarize non-empty requires a non-empty summary string.
    """
    keep = _int_list(plan.get("keep"))
    summarize = _int_list(plan.get("summarize"))
    drop = _int_list(plan.get("drop"))
    if keep is None or summarize is None or drop is None:
        return False
    count = len(segments)
    ids = keep + summarize + drop
    if any(not 0 <= i < count for i in ids):
        return False
    if len(set(ids)) != len(ids):
        return False
    for i, (begin, end) in enumerate(segments):
        all_system = all(messages[m].get("role") == "system" for m in range(begin, end))
        if all_system and i not in keep:
            return False
    if count - 1 not in keep:
        return False
    return not (summarize and not str(plan.get("summary") or "").strip())


def apply_plan(
    messages: list[dict[str, Any]],
    segments: list[tuple[int, int]],
    plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build the restructured transcript: kept segments verbatim, the summary
    user message at the first summarized segment's position, dropped segments
    omitted. Unlisted segments default to kept. Returns a new list; the caller
    assigns it in place.

    Shrink guard: a summary that would not be smaller than the content it
    replaces is refused and those segments stay verbatim — "compression" that
    grows the transcript is worse than no compaction.
    """
    summarize = set(plan.get("summarize") or ())
    summary = str(plan.get("summary") or "").strip()
    if summarize and summary:
        source_chars = sum(
            len(str(m.get("content") or ""))
            for idx in summarize
            for m in messages[segments[idx][0] : segments[idx][1]]
        )
        if len(summary) + len(SUMMARY_MARK) >= source_chars:
            summarize = set()  # refused: the source is the smaller side, keep it
    out: list[dict[str, Any]] = []
    summary_written = False
    for idx, (begin, end) in enumerate(segments):
        if idx in summarize:
            if not summary_written:
                out.append({"role": "user", "content": f"{SUMMARY_MARK} {summary}"})
                summary_written = True
            continue
        if idx in (set(plan.get("drop") or ())):
            continue
        out.extend(messages[begin:end])
    return out


def drop_ids(plan: dict[str, Any]) -> set[int]:
    return set(plan.get("drop") or ())


def _plan_report(
    *,
    mode: str,
    before: int,
    after: int,
    target: int,
    kept: int,
    summarized: int,
    dropped: int,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "before_tokens": before,
        "after_tokens": after,
        "target_tokens": target,
        "kept": kept,
        "summarized": summarized,
        "dropped": dropped,
    }


async def compact_transcript(
    messages: list[dict[str, Any]],
    llm: LLMClient,
    *,
    target: int,
    fallback_budget: int | None = None,
) -> dict[str, Any] | None:
    """Restructure the transcript in place under the target token estimate.

    Returns a report dict, or None when the transcript is already within
    target (no planner call is spent). The plan path is primary; any failure
    (planner error, invalid plan, plan result still over target) falls back to
    deterministic compress, which itself is pair-safe - the loop never breaks
    because of a failed compaction.
    """
    before = estimate_messages(messages)
    if before <= target:
        return None
    segments = iter_segments(messages)
    plan: dict[str, Any] | None = None
    try:
        # Prefix-cache friendly request: the conversation is replayed
        # verbatim (the provider prefix cache built by the main conversation
        # still hits) and the planning instruction rides one tail message --
        # never a rewritten copy of the transcript.
        reply = await llm.complete(
            [
                *messages,
                {"role": "user", "content": _PLAN_PROMPT + render_segment_map(segments)},
            ]
        )
        if not reply.degraded:
            plan = parse_plan(reply.text or "")
    except Exception:  # planner failure falls back, never crashes
        log.warning("context editor planner call failed; falling back", exc_info=True)
        plan = None

    if plan is not None and validate_plan(plan, segments, messages):
        candidate = apply_plan(messages, segments, plan)
        after = estimate_messages(candidate)
        if after <= target:
            messages[:] = candidate
            kept = len(segments) - len(set(plan.get("summarize") or ())) - len(drop_ids(plan))
            return _plan_report(
                mode="plan",
                before=before,
                after=after,
                target=target,
                kept=kept,
                summarized=len(set(plan.get("summarize") or ())),
                dropped=len(drop_ids(plan)),
            )
        log.info("editor plan left %d tokens over target %d; falling back", after, target)

    budget = fallback_budget if fallback_budget is not None else target
    messages[:] = compress(messages, budget=budget, prune=True)
    return _plan_report(
        mode="fallback",
        before=before,
        after=estimate_messages(messages),
        target=target,
        kept=0,
        summarized=0,
        dropped=0,
    )


__all__ = ["SUMMARY_MARK", "compact_transcript", "iter_segments", "parse_plan", "validate_plan"]
