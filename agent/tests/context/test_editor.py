"""Tests for the LLM-driven context editor: pair-shaped segmentation,
the keep/summarize/drop plan protocol, harness-side validation, deterministic
fallback, and the governor's threshold gating.
"""

import json

from agent.context.backoff import CompactionBackoff
from agent.context.editor import (
    SUMMARY_MARK,
    apply_plan,
    compact_transcript,
    iter_segments,
    parse_plan,
    validate_plan,
)
from agent.context.governor import ContextGovernor
from agent.context.usage import ContextWindow, UsageTracker
from agent.llm import FakeLLM, LLMReply
from agent.subagent import Mode, ModeLimits, run_mode


def _msgs() -> list[dict]:
    """system + 3 pair-shaped rounds + a final question. Segments:
    0=system, 1=user0, 2=assistant0+tool0, 3=user1, 4=assistant1+tool1,
    5=user2, 6=assistant2+tool2, 7=final user."""
    msgs: list[dict] = [{"role": "system", "content": "system prompt"}]
    for i in range(3):
        msgs.append({"role": "user", "content": f"round {i} task " + "bg " * 60})
        msgs.append(
            {
                "role": "assistant",
                "content": "calling",
                "tool_calls": [{"id": f"c{i}", "name": "t", "arguments": {}}],
            }
        )
        msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": "result " * 80})
    msgs.append({"role": "user", "content": "final question"})
    return msgs


def _pairs_intact(msgs: list[dict]) -> bool:
    for idx, m in enumerate(msgs):
        if m.get("role") == "tool":
            prev = msgs[idx - 1] if idx else None
            if not prev or "tool_calls" not in prev:
                return False
        if m.get("role") == "assistant" and m.get("tool_calls"):
            calls = len(m["tool_calls"])
            results = 0
            for nxt in msgs[idx + 1 :]:
                if nxt.get("role") == "tool":
                    results += 1
                else:
                    break
            if results != calls:
                return False
    return True


class TestSegments:
    def test_pairs_are_atomic(self) -> None:
        msgs = _msgs()
        segments = iter_segments(msgs)
        assert (0, 1) == segments[0]  # system
        assert (1, 2) == segments[1]  # user alone
        assert (2, 4) == segments[2]  # assistant + tool atomic
        assert segments[-1] == (len(msgs) - 1, len(msgs))

    def test_orphan_tool_is_own_segment(self) -> None:
        segments = iter_segments([{"role": "tool", "tool_call_id": "x", "content": "y"}])
        assert segments == [(0, 1)]


class TestCompactTranscript:
    async def test_no_op_within_target(self) -> None:
        llm = FakeLLM()
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]
        assert await compact_transcript(msgs, llm, target=100_000) is None
        assert llm.calls == []

    async def test_valid_plan_applied(self) -> None:
        plan = json.dumps(
            {
                "keep": [0, 2, 4, 6, 7],
                "summarize": [1],
                "drop": [3],
                "summary": "目标:测试;已完成:三轮;下一步:回答",
            }
        )
        llm = FakeLLM([LLMReply(text=plan)])
        msgs = _msgs()
        # before ~641 tokens (3 tool rows dominate); the plan keeps the three
        # pairs + system + final + summary (~524) -> fits under 600
        report = await compact_transcript(msgs, llm, target=600)
        assert report is not None
        assert report is not None
        assert report["mode"] == "plan"
        assert report["summarized"] == 1 and report["dropped"] == 1
        texts = [str(m.get("content")) for m in msgs]
        assert any(SUMMARY_MARK in t for t in texts)
        # The final user message survives (last segment forced keep in plan)
        assert "final question" in " ".join(texts)
        assert _pairs_intact(msgs)

    async def test_garbage_reply_falls_back(self) -> None:
        llm = FakeLLM([LLMReply(text="我觉得可以直接删掉一半吧")])
        msgs = _msgs()
        report = await compact_transcript(msgs, llm, target=10, fallback_budget=200)
        assert report is not None
        assert report["mode"] == "fallback"
        assert _pairs_intact(msgs)

    async def test_planner_exception_falls_back(self) -> None:
        class _Boom:
            async def complete(self, messages, tools=None):
                raise RuntimeError("planner down")

        msgs = _msgs()
        report = await compact_transcript(msgs, _Boom(), target=10, fallback_budget=200)
        assert report is not None
        assert report["mode"] == "fallback"
        assert _pairs_intact(msgs)

    async def test_invalid_plans_fall_back(self) -> None:
        bad_plans = [
            '{"keep": [0, 99], "summarize": [], "drop": []}',  # out of range
            '{"keep": [1, 1], "summarize": [], "drop": []}',  # duplicate
            '{"keep": [0], "summarize": [1], "drop": [3], "summary": ""}',  # no summary text
            '{"keep": [0], "summarize": [], "drop": [4]}',  # last segment dropped
            '{"keep": "all", "summarize": [], "drop": []}',  # wrong type
        ]
        for raw in bad_plans:
            llm = FakeLLM([LLMReply(text=raw)])
            msgs = _msgs()
            report = await compact_transcript(msgs, llm, target=10, fallback_budget=5_000)
            assert report is not None
            assert report["mode"] == "fallback", raw
            assert _pairs_intact(msgs)

    async def test_plan_over_target_falls_back(self) -> None:
        # Keep everything: valid plan but the transcript stays over target
        plan = json.dumps({"keep": [0, 1, 2, 3, 4], "summarize": [], "drop": []})
        llm = FakeLLM([LLMReply(text=plan)])
        msgs = _msgs()
        report = await compact_transcript(msgs, llm, target=10, fallback_budget=300)
        assert report is not None
        assert report["mode"] == "fallback"
        assert _pairs_intact(msgs)

    async def test_degraded_reply_falls_back(self) -> None:
        llm = FakeLLM([LLMReply(text="quota", degraded=True)])
        msgs = _msgs()
        report = await compact_transcript(msgs, llm, target=10, fallback_budget=300)
        assert report is not None
        assert report["mode"] == "fallback"


class TestApplyPlan:
    def test_uncovered_defaults_to_keep(self) -> None:
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        segments = iter_segments(msgs)
        out = apply_plan(msgs, segments, {"keep": [], "summarize": [], "drop": [1], "summary": ""})
        assert [m["content"] for m in out] == ["s", "b"]


class TestGovernor:
    def _governor(self, llm, **kw) -> ContextGovernor:
        defaults = {
            "window": ContextWindow(window_tokens=2_000, max_output_tokens=500),
            "auto_compact_at": 75,
            "compact_target": 0,
            "fallback_budget": 300,
            "tracker": UsageTracker(),
            "llm": llm,
        }
        defaults.update(kw)
        return ContextGovernor(**defaults)

    def test_target_auto_is_40pct_usable(self) -> None:
        assert self._governor(FakeLLM()).target_tokens() == int(1_500 * 0.4)

    def test_target_explicit_overrides(self) -> None:
        assert self._governor(FakeLLM(), compact_target=777).target_tokens() == 777

    async def test_enforce_skips_under_threshold(self) -> None:
        llm = FakeLLM()
        gov = self._governor(llm)
        msgs = [{"role": "user", "content": "tiny"}]
        assert await gov.enforce(msgs) is None
        assert llm.calls == []

    async def test_enforce_fires_over_threshold(self) -> None:
        plan = json.dumps({"keep": [0, 2], "summarize": [], "drop": [1]})
        llm = FakeLLM([LLMReply(text=plan)])
        gov = self._governor(llm)
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "word " * 900},  # > 75% of 1500 usable
            {"role": "user", "content": "final question"},
        ]
        report = await gov.enforce(msgs)
        assert report is not None and report["mode"] == "plan"
        assert len(llm.calls) == 1  # exactly one planner call

    async def test_planner_client_receives_the_editor_call(self) -> None:
        """With the context_planner route injected, the planning call goes to
        the routed (lighter) client and the chat client is never spent."""
        plan = json.dumps({"keep": [0, 2], "summarize": [], "drop": [1]})
        chat = FakeLLM()
        planner = FakeLLM([LLMReply(text=plan)])
        gov = self._governor(chat, planner=planner)
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "word " * 900},
            {"role": "user", "content": "final question"},
        ]
        report = await gov.enforce(msgs)
        assert report is not None and report["mode"] == "plan"
        assert len(planner.calls) == 1
        assert chat.calls == []

    async def test_repeated_failures_take_the_mechanical_path(self) -> None:
        """After two failing LLM compactions the guard suppresses the planner:
        the next compact runs mechanically (mode="mechanical") and the planner
        client is not called again."""

        class _Boom:
            async def complete(self, messages, tools=None):
                raise RuntimeError("planner down")

        gov = self._governor(FakeLLM(), planner=_Boom(), guard=CompactionBackoff())
        msgs = _msgs()
        for _ in range(2):
            report = await gov.compact(msgs, target=10)
            assert report is not None and report["mode"] == "fallback"
        report = await gov.compact(msgs, target=10)
        assert report is not None and report["mode"] == "mechanical"

    async def test_no_attempt_records_nothing(self) -> None:
        """A compact that no-ops (already within target) must not consume
        backoff slots or count as a failure."""
        guard = CompactionBackoff()
        gov = self._governor(FakeLLM(), guard=guard)
        msgs = [{"role": "user", "content": "tiny"}]
        assert await gov.compact(msgs, target=100_000) is None
        assert guard.allow_llm() is True


class TestReactIntegration:
    async def test_threshold_triggers_editor_before_round(self) -> None:
        # Segments: 0=system, 1=user(long), 2=assistant, 3=user(final)
        plan = json.dumps(
            {
                "keep": [0, 2, 3],
                "summarize": [1],
                "drop": [],
                "summary": "旧任务已完成,结论为继续;当前问题:最终问句",
            }
        )
        llm = FakeLLM(
            [
                LLMReply(text=plan),  # planner call (harness-initiated)
                LLMReply(text="done"),  # round 1 completion
            ]
        )
        msgs = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "old task " + "bg " * 400},
            {"role": "assistant", "content": "noted"},
            {"role": "user", "content": "final question"},
        ]
        governor = ContextGovernor(
            window=ContextWindow(window_tokens=3_000, max_output_tokens=500),
            auto_compact_at=5,  # tiny threshold: fires immediately
            compact_target=100,  # below the threshold's token size, so compact acts
            fallback_budget=300,
            tracker=UsageTracker(),
            llm=llm,
        )
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=None,
            messages=msgs,
            limits=ModeLimits(),
            governor=governor,
        )
        assert result == "done"
        # Call 0 = planner (rendered segments), call 1 = the real completion
        assert "段0" in str(llm.calls[0]["messages"][-1]["content"])
        transcript = " ".join(str(m.get("content")) for m in msgs)
        assert SUMMARY_MARK in transcript
        assert _pairs_intact(msgs)


class TestParsePlan:
    def test_tolerates_fenced_block(self) -> None:
        raw = '```json\n{"keep": [0], "summarize": [], "drop": [], "summary": ""}\n```'
        plan = parse_plan(raw)
        assert plan == {"keep": [0], "summarize": [], "drop": [], "summary": ""}

    def test_non_json_is_none(self) -> None:
        assert parse_plan("nope") is None


class TestValidate:
    def test_system_segment_forced_keep(self) -> None:
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
        segments = iter_segments(msgs)
        plan = {"keep": [1], "summarize": [], "drop": [0], "summary": ""}
        assert validate_plan(plan, segments, msgs) is False
