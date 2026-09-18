"""Rolling tool-result prune (microcompact): protect-recent economics,
recovery floor, pairing safety, and the governor wiring (prune report +
anchor reset + the low-yield plan guard feeding the backoff)."""

from __future__ import annotations

from typing import Any

from agent.context.backoff import CompactionBackoff
from agent.context.governor import MAX_REMAINING_RATIO, ContextGovernor
from agent.context.prune import PRUNE_MARK, prune_tool_results
from agent.context.usage import ContextWindow, UsageTracker
from agent.llm import FakeLLM, LLMReply


def _big(content: str, chars: int) -> str:
    return f"{content}-" * max(1, chars // (len(content) + 1))


def _transcript(old_a: str, old_b: str, recent: str) -> list[dict]:
    """system + two prunable old turns + the protected recent tail."""
    return [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "old question 1"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "1", "name": "web_fetch", "arguments": {}}],
        },
        {"role": "tool", "tool_call_id": "1", "name": "web_fetch", "content": old_a},
        {"role": "user", "content": "old question 2"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "2", "name": "web_fetch", "arguments": {}}],
        },
        {"role": "tool", "tool_call_id": "2", "name": "web_fetch", "content": old_b},
        {"role": "user", "content": "new question"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "3", "name": "web_fetch", "arguments": {}}],
        },
        {"role": "tool", "tool_call_id": "3", "name": "web_fetch", "content": recent},
        {"role": "user", "content": "latest question"},
    ]


class TestPruneToolResults:
    def test_clears_old_results_protects_fitting_suffix(self) -> None:
        old_a = _big("a", 6000)  # ~1500 tokens: exceeds any small window
        old_b = _big("b", 400)  # ~100 tokens: fits a 100-token window
        recent = _big("r", 4000)  # inside the protected tail anyway
        msgs = _transcript(old_a, old_b, recent)
        recovered = prune_tool_results(msgs, protect_tokens=100, min_tokens=10)
        assert recovered > 0
        # The oversized old result is truncated to the sentinel...
        assert msgs[3]["content"] == old_a[:80] + PRUNE_MARK
        # ...the newest old result fits the protect window and stays intact...
        assert msgs[6]["content"] == old_b
        # ...and the protected tail is untouched
        assert msgs[9]["content"] == recent
        # Pairing survives: roles and ids unchanged
        assert [m["tool_call_id"] for m in msgs if m.get("role") == "tool"] == ["1", "2", "3"]

    def test_recovery_floor_blocks_tiny_prunes(self) -> None:
        msgs = _transcript(_big("x", 4000), _big("y", 4000), _big("r", 400))
        assert prune_tool_results(msgs, protect_tokens=100, min_tokens=100_000) == 0
        assert msgs[3]["content"] == _big("x", 4000)  # untouched

    def test_short_results_never_cleared(self) -> None:
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "old"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "1", "name": "t", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "1", "name": "t", "content": "short result"},
            {"role": "user", "content": "new"},
        ]
        assert prune_tool_results(msgs, protect_tokens=1, min_tokens=1) == 0
        assert msgs[3]["content"] == "short result"

    def test_keep_turns_boundary_protects_tail(self) -> None:
        big = _big("z", 50_000)
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "solo turn"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "1", "name": "t", "arguments": {}}],
            },
            {"role": "tool", "tool_call_id": "1", "name": "t", "content": big},
        ]
        # The only turn is inside the protected tail: nothing to clear
        assert prune_tool_results(msgs, protect_tokens=1, min_tokens=1, keep_turns=2) == 0


class TestGovernorPruneWiring:
    def _governor(self, llm, **kw) -> ContextGovernor:
        defaults = {
            "window": ContextWindow(window_tokens=2_000, max_output_tokens=500),
            "auto_compact_at": 75,
            "compact_target": 0,
            "fallback_budget": 300,
            "tracker": UsageTracker(),
            "llm": llm,
            "prune_protect_tokens": 100,
            "prune_min_tokens": 10,
        }
        defaults.update(kw)
        return ContextGovernor(**defaults)

    async def test_prune_report_when_under_compact_threshold(self) -> None:
        llm = FakeLLM()
        tracker = UsageTracker()
        gov = self._governor(llm, tracker=tracker)
        tracker.record(10)  # well under the compact trigger
        msgs = _transcript(_big("a", 6000), _big("b", 400), _big("r", 400))
        report = await gov.enforce(msgs)
        assert report is not None and report["mode"] == "prune"
        assert report["recovered_tokens"] > 0
        # The cleared prefix invalidated the provider anchor
        assert tracker.last_reported == 0
        assert llm.calls == []  # no planner call spent

    async def test_low_yield_plan_counts_as_guard_failure(self) -> None:
        """A plan that leaves more than MAX_REMAINING_RATIO of the transcript
        feeds the backoff as a failure, so repeated low-yield planner calls
        get suppressed and the mechanical path takes over."""
        from agent.context.tokenizer import estimate_messages

        plan = '{"keep": [0, 1, 3], "summarize": [], "drop": [2], "summary": ""}'
        # threshold=1: a single low-yield plan immediately opens suppression
        guard = CompactionBackoff(threshold=1)
        llm = FakeLLM([LLMReply(text=plan)])
        gov = self._governor(llm, guard=guard, planner=llm)
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "word " * 1300},
            {"role": "assistant", "content": "okok okok"},  # dropping this shrinks ~2 tokens
            {"role": "user", "content": "final"},
        ]
        # target sits just below `before`, so dropping the tiny assistant entry
        # is accepted (after <= target) while shrinking far less than the ratio
        target = estimate_messages(msgs) - 1
        first = await gov.compact(msgs, target=target)
        assert first is not None and first["mode"] == "plan"
        assert first["after_tokens"] > int(first["before_tokens"] * MAX_REMAINING_RATIO)
        assert len(llm.calls) == 1
        # New input pushes the transcript over the target again; the low-yield
        # failure recorded by the first plan suppresses the planner: the next
        # compaction runs mechanically without a second planner call
        msgs.append({"role": "user", "content": "more " * 400})
        second = await gov.compact(msgs, target=target)
        assert second is not None and second["mode"] == "mechanical"
        assert len(llm.calls) == 1
