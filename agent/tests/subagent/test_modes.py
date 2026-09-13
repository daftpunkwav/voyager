"""Tests for the seven mode execution strategies: the ReAct loop, round/tool
dual caps, and each mode call shape.
"""

import asyncio
from typing import Any

import pytest
from agent.llm import FakeLLM, LLMReply, ToolCall, Usage
from agent.policy import PolicyEngine
from agent.subagent import Mode, ModeLimits, run_mode
from agent.tools import AgentTool, Toolbelt


def _belt() -> Toolbelt:
    async def echo_tool(x: str = "") -> str:
        return f"echo:{x}"

    return Toolbelt(
        {"echo_tool": AgentTool(name="echo_tool", description="测试工具", handler=echo_tool)},
        PolicyEngine(),
    )


def _msgs() -> list[dict]:
    return [{"role": "user", "content": "任务"}]


class TestReAct:
    async def test_tool_then_final(self) -> None:
        llm = FakeLLM(
            [
                LLMReply(tool_calls=(ToolCall("1", "echo_tool", {"x": "a"}),)),
                LLMReply(text="完成"),
            ]
        )
        messages = _msgs()
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=_belt(), messages=messages, limits=ModeLimits()
        )
        assert result == "完成"
        # Neutral backfill: assistant carries tool_calls, results reuse the same ids, order user -> assistant -> tool
        assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
        assert messages[1]["tool_calls"] == [
            {"id": "1", "name": "echo_tool", "arguments": {"x": "a"}}
        ]
        assert messages[2]["tool_call_id"] == "1"
        assert messages[2]["content"] == "echo:a"

    async def test_multiple_calls_paired_in_order(self) -> None:
        """Multiple calls in one round: one assistant plus several tool rows in matching order, with no user/system rows interleaved."""
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall("1", "echo_tool", {"x": "a"}),
                        ToolCall("2", "echo_tool", {"x": "b"}),
                    )
                ),
                LLMReply(text="完成"),
            ]
        )
        messages = _msgs()
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=_belt(), messages=messages, limits=ModeLimits()
        )
        assert result == "完成"
        assert [m["role"] for m in messages] == ["user", "assistant", "tool", "tool"]
        assert messages[1]["tool_calls"] == [
            {"id": "1", "name": "echo_tool", "arguments": {"x": "a"}},
            {"id": "2", "name": "echo_tool", "arguments": {"x": "b"}},
        ]
        assert [m["tool_call_id"] for m in messages[2:]] == ["1", "2"]

    async def test_rounds_limit(self) -> None:
        llm = FakeLLM(dynamic=lambda _m, _t: LLMReply(tool_calls=(ToolCall("1", "echo_tool", {}),)))
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=_msgs(),
            limits=ModeLimits(max_rounds=2),
        )
        assert result.startswith("[中断] 已达 ReAct 轮数上限")

    async def test_tool_calls_limit(self) -> None:
        llm = FakeLLM(
            [LLMReply(tool_calls=(ToolCall("1", "echo_tool", {}), ToolCall("2", "echo_tool", {})))]
        )
        messages = _msgs()
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=messages,
            limits=ModeLimits(max_tool_calls=1),
        )
        assert result.startswith("[中断] 已达工具调用上限")
        # Truncation: only the first call runs; assistant.tool_calls drops the unexecuted "2", leaving no call-without-result
        assert [m["role"] for m in messages] == ["user", "assistant", "tool"]
        assert [tc["id"] for tc in messages[1]["tool_calls"]] == ["1"]
        assert messages[2]["tool_call_id"] == "1"

    async def test_tool_calls_without_toolbelt(self) -> None:
        llm = FakeLLM([LLMReply(tool_calls=(ToolCall("1", "echo_tool", {}),))])
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
        )
        assert "无工具可用" in result

    async def test_zero_tool_final_continues_react_loop(self) -> None:
        """Non-small-talk text with zero tool calls is not final: the same loop completes again instead of scanning for agreement."""
        llm = FakeLLM(
            [
                LLMReply(text="行。"),  # contains no agreement phrases
                LLMReply(tool_calls=(ToolCall("1", "echo_tool", {"x": "a"}),)),
                LLMReply(text="echo 完了"),
            ]
        )
        messages = [{"role": "user", "content": "都测试一下"}]
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=messages,
            limits=ModeLimits(),
            continue_if_idle=True,
        )
        assert result == "echo 完了"
        assert len(llm.calls) == 3
        assert any("[react]" in str(m.get("content", "")) for m in messages)

    async def test_compresses_over_budget_before_complete(self) -> None:
        """Compression before each complete: over-budget old tool results are truncated, system is kept."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "任务"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}]},
            {"role": "tool", "tool_call_id": "a", "content": "旧结果" * 9000},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "b"}]},
            {"role": "tool", "tool_call_id": "b", "content": "次新结果" * 9000},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c"}]},
            {"role": "tool", "tool_call_id": "c", "content": "最新结果" * 9000},
            {"role": "user", "content": "收尾"},
        ]
        llm = FakeLLM([LLMReply(text="完成")])
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=None, messages=messages, limits=ModeLimits()
        )
        assert result == "完成"
        sent = llm.calls[0]["messages"]
        assert sent[0]["role"] == "system" and sent[0]["content"] == "系统提示"
        assert "已压缩" in sent[3]["content"] and len(sent[3]["content"]) < 200
        assert sent[5]["content"] == "次新结果" * 9000  # untouched within the most recent 4
        assert sent[7]["content"] == "最新结果" * 9000
        assert len(sent) == len(messages)  # truncate only, no drops: tool pairs stay intact

    async def test_chitchat_without_tools_does_not_nudge(self) -> None:
        llm = FakeLLM([LLMReply(text="你好,我在。")])
        messages = [{"role": "user", "content": "你好"}]
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=messages,
            limits=ModeLimits(),
            continue_if_idle=True,
        )
        assert result == "你好,我在。"
        assert len(llm.calls) == 1

    async def test_nudge_declined_delivers_pre_nudge_answer(self) -> None:
        """Model answers in round 1, nudge fires (non-chitchat, zero tools), model
        declines tools in round 2: the pre-nudge answer is delivered, not the
        forced "no tool needed" justification the nudge itself induced."""
        llm = FakeLLM(
            [
                LLMReply(text="我是 Lucien,这个工作台的常驻统筹者。"),
                LLMReply(text="当前无需调用工具——闲聊已有上下文能直接答完。"),
            ]
        )
        messages = [{"role": "user", "content": "你是谁?"}]
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=messages,
            limits=ModeLimits(),
            continue_if_idle=True,
        )
        assert result == "我是 Lucien,这个工作台的常驻统筹者。"
        assert len(llm.calls) == 2  # nudge still happened (forcing is intact)
        assert any("[react]" in str(m.get("content", "")) for m in messages)

    async def test_nudge_then_tools_still_returns_post_tool_answer(self) -> None:
        """After the nudge the model picks up a tool: the post-tool answer wins,
        the pre-nudge text must not shadow it."""
        llm = FakeLLM(
            [
                LLMReply(text="我先查一下。"),
                LLMReply(tool_calls=(ToolCall("1", "echo_tool", {"x": "a"}),)),
                LLMReply(text="echo 完了"),
            ]
        )
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(),
            messages=[{"role": "user", "content": "都测试一下"}],
            limits=ModeLimits(),
            continue_if_idle=True,
        )
        assert result == "echo 完了"


class TestOtherModes:
    async def test_cot_plan_steps_synthesis(self) -> None:
        """COT: plan -> per-step execution -> synthesis, one budget across
        phases; the plan and each step ride the shared transcript."""
        llm = FakeLLM(
            [
                LLMReply(text="1. 收集资料\n2. 撰写结论"),
                LLMReply(text="资料在手"),
                LLMReply(text="结论成立"),
                LLMReply(text="最终答案:成立"),
            ]
        )
        result = await run_mode(
            Mode.COT, llm=llm, toolbelt=_belt(), messages=_msgs(), limits=ModeLimits()
        )
        assert result == "最终答案:成立"
        assert len(llm.calls) == 4  # plan + 2 steps + synthesis
        # plan request carries the reasoning hint
        assert "逐步推理" in llm.calls[0]["messages"][0]["content"]
        # steps addressed on the shared transcript
        assert any("【步骤 1/2】" in str(m.get("content")) for m in llm.calls[1]["messages"])
        assert any("【步骤 2/2】" in str(m.get("content")) for m in llm.calls[2]["messages"])

    async def test_cot_unparseable_plan_degrades_to_one_step(self) -> None:
        llm = FakeLLM(
            [LLMReply(text="直接做完即可"), LLMReply(text="步骤结论"), LLMReply(text="做完了")]
        )
        result = await run_mode(
            Mode.COT, llm=llm, toolbelt=_belt(), messages=_msgs(), limits=ModeLimits()
        )
        assert result == "做完了"
        assert len(llm.calls) == 3  # plan + 1 (merged) step + synthesis

    async def test_cot_token_budget_stops_steps_but_reports(self) -> None:
        llm = FakeLLM(
            [
                LLMReply(text="1. 甲\n2. 乙", usage=Usage(input_tokens=900, output_tokens=100)),
                LLMReply(text="甲完成", usage=Usage(input_tokens=900, output_tokens=100)),
                LLMReply(text="乙完成", usage=Usage(input_tokens=900, output_tokens=100)),
            ]
        )
        result = await run_mode(
            Mode.COT,
            llm=llm,
            toolbelt=_belt(),
            messages=_msgs(),
            limits=ModeLimits(max_tokens=1500),
        )
        assert result.startswith("[预算]")
        assert "1/2 步完成" in result

    async def test_cot_round_cap_skips_remaining_steps(self) -> None:
        """The invocation round cap is honored across phases: plan + one step
        spend max_rounds=2, the remaining step is skipped and named to the
        closing synthesis (which still runs as the grace completion)."""
        llm = FakeLLM(
            [
                LLMReply(text="1. 甲\n2. 乙"),
                LLMReply(text="甲完成"),
                LLMReply(text="综合收尾"),
            ]
        )
        result = await run_mode(
            Mode.COT, llm=llm, toolbelt=_belt(), messages=_msgs(), limits=ModeLimits(max_rounds=2)
        )
        assert result == "综合收尾"
        synthesis_input = llm.calls[2]["messages"]
        assert any("因预算限制未执行的步骤:乙" in str(m.get("content")) for m in synthesis_input)

    async def test_plan_execute_steps_and_report(self) -> None:
        """PLAN_EXECUTE: plan persists to the transcript, steps execute in
        order, the final report closes the invocation."""
        llm = FakeLLM(
            [
                LLMReply(text="1. 第一步\n2. 第二步"),
                LLMReply(text="第一步完成"),
                LLMReply(text="第二步完成"),
                LLMReply(text="全部完成"),
            ]
        )
        result = await run_mode(
            Mode.PLAN_EXECUTE, llm=llm, toolbelt=_belt(), messages=_msgs(), limits=ModeLimits()
        )
        assert result == "全部完成"
        assert len(llm.calls) == 4
        # the plan is fed back into the execute phase (assistant entry)
        assert any(
            m.get("role") == "assistant" and "第一步" in str(m.get("content"))
            for m in llm.calls[1]["messages"]
        )

    async def test_plan_execute_replans_after_failed_step(self) -> None:
        """A step whose slice aborts triggers one bounded replan that replaces
        the remaining steps; the report still ships."""
        llm = FakeLLM(
            [
                LLMReply(text="1. 会失败的步骤\n2. 旧计划步骤"),
                # the step slice keeps asking for the same call; the third
                # identical call trips the loop guard with an empty executable
                # prefix, which aborts the slice immediately
                LLMReply(tool_calls=(ToolCall("1", "echo_tool", {"x": "a"}),)),
                LLMReply(tool_calls=(ToolCall("2", "echo_tool", {"x": "a"}),)),
                LLMReply(tool_calls=(ToolCall("3", "echo_tool", {"x": "a"}),)),
                LLMReply(text="1. 新方法"),  # replan
                LLMReply(text="新方法完成"),
                LLMReply(text="按新计划完成"),
            ]
        )
        result = await run_mode(
            Mode.PLAN_EXECUTE,
            llm=llm,
            toolbelt=_belt(),
            messages=_msgs(),
            limits=ModeLimits(max_rounds=20, max_tool_calls=40),
        )
        assert result == "按新计划完成"
        # replan request saw the abort note and the remaining steps
        assert any("剩余未执行步骤" in str(m.get("content")) for m in llm.calls[4]["messages"])

    async def test_reflexion_revise_then_accept(self) -> None:
        """REFLEXION: REVISE verdict retries with the lessons visible; the
        final attempt is delivered without further review spend."""
        llm = FakeLLM(
            [
                LLMReply(text="草稿"),
                LLMReply(text="REVISE:缺少验证步骤\n1. 先验证"),
                LLMReply(text="修订版"),
            ]
        )
        result = await run_mode(
            Mode.REFLEXION, llm=llm, toolbelt=_belt(), messages=_msgs(), limits=ModeLimits()
        )
        assert result == "修订版"
        assert len(llm.calls) == 3  # draft + review + retry (no second review)
        # the retry saw the reflection entry
        assert any("【反思】" in str(m.get("content")) for m in llm.calls[2]["messages"])

    async def test_reflexion_adequate_verdict_keeps_draft(self) -> None:
        llm = FakeLLM([LLMReply(text="草稿"), LLMReply(text="ADEQUATE:已充分")])
        result = await run_mode(
            Mode.REFLEXION, llm=llm, toolbelt=_belt(), messages=_msgs(), limits=ModeLimits()
        )
        assert result == "草稿"
        assert len(llm.calls) == 2

    async def test_reflexion_unreadable_review_keeps_draft(self) -> None:
        """An empty/unparseable review must not destroy a finished attempt."""
        llm = FakeLLM([LLMReply(text="草稿"), LLMReply(text="嗯,看看再说")])
        result = await run_mode(
            Mode.REFLEXION, llm=llm, toolbelt=_belt(), messages=_msgs(), limits=ModeLimits()
        )
        assert result == "草稿"

    async def test_tot_rank_expand_pick(self) -> None:
        """TOT: 3 candidates ranked by JSON verdict, top-2 expanded, winner
        picked, final answer streamed out."""
        llm = FakeLLM(
            [
                LLMReply(text="候选A"),
                LLMReply(text="候选B"),
                LLMReply(text="候选C"),
                LLMReply(text='{"ranking": ["B", "A", "C"]}'),
                LLMReply(text="B 展开"),
                LLMReply(text="A 展开"),
                LLMReply(text='{"best": "A"}'),
                LLMReply(text="最终答案"),
            ]
        )
        result = await run_mode(
            Mode.TOT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
        )
        assert result == "最终答案"
        assert len(llm.calls) == 8
        # judge saw the lettered candidates
        assert "[A]" in llm.calls[3]["messages"][-1]["content"]
        # expansion used the ranked order (B first, then A)
        assert "方案 B" in llm.calls[4]["messages"][0]["content"]
        assert "方案 A" in llm.calls[5]["messages"][0]["content"]

    async def test_tot_malformed_judge_falls_back_to_order(self) -> None:
        llm = FakeLLM(
            [
                LLMReply(text="候选A"),
                LLMReply(text="候选B"),
                LLMReply(text="候选C"),
                LLMReply(text="我觉得都行"),  # not JSON: original order wins
                LLMReply(text="A 展开"),
                LLMReply(text="B 展开"),
                LLMReply(text='{"best": "B"}'),
                LLMReply(text="最终"),
            ]
        )
        result = await run_mode(
            Mode.TOT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
        )
        assert result == "最终"
        assert "方案 A" in llm.calls[4]["messages"][0]["content"]  # A stays first

    async def test_got_angles_aggregate_refine(self) -> None:
        """GOT: fixed angle menu in parallel, explicit aggregation, one
        refinement pass; the refined draft is the answer (no tools)."""
        llm = FakeLLM(
            [
                LLMReply(text="正确性产出"),
                LLMReply(text="完整性产出"),
                LLMReply(text="风险产出"),
                LLMReply(text="可行性产出"),
                LLMReply(text="聚合稿"),
                LLMReply(text="修订稿"),
            ]
        )
        result = await run_mode(
            Mode.GOT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
        )
        assert result == "修订稿"
        assert len(llm.calls) == 6
        aggregate_input = llm.calls[4]["messages"][-1]["content"]
        assert "【正确性与事实核查】" in aggregate_input
        assert "【可行性与成本】" in aggregate_input
        refine_input = llm.calls[5]["messages"]
        assert any(
            "聚合稿" == str(m.get("content")) for m in refine_input if m.get("role") == "assistant"
        )

    async def test_got_budget_collapse_still_delivers_aggregate(self) -> None:
        """When the token budget is spent before aggregation, the first angle
        output ships as best-so-far instead of an error."""
        llm = FakeLLM(
            [
                LLMReply(text="角度1", usage=Usage(input_tokens=800, output_tokens=200)),
                LLMReply(text="角度2", usage=Usage(input_tokens=800, output_tokens=200)),
                LLMReply(text="角度3", usage=Usage(input_tokens=800, output_tokens=200)),
                LLMReply(text="角度4", usage=Usage(input_tokens=800, output_tokens=200)),
            ]
        )
        result = await run_mode(
            Mode.GOT,
            llm=llm,
            toolbelt=None,
            messages=_msgs(),
            limits=ModeLimits(max_tokens=3000),
        )
        assert result.startswith("[预算]")
        assert "角度1" in result

    async def test_direct_single_call(self) -> None:
        llm = FakeLLM([LLMReply(text="直答")])
        assert (
            await run_mode(
                Mode.DIRECT, llm=llm, toolbelt=None, messages=_msgs(), limits=ModeLimits()
            )
            == "直答"
        )
        assert len(llm.calls) == 1

    async def test_unknown_mode(self) -> None:
        with pytest.raises(ValueError, match="未知模式"):
            await run_mode(
                "nope",  # type: ignore[arg-type]  # intentionally invalid: not a Mode
                llm=FakeLLM(),
                toolbelt=None,
                messages=_msgs(),
                limits=ModeLimits(),
            )

    async def test_overflow_recovers_with_aggressive_compact(self) -> None:
        """A context-overflow reply triggers one aggressive compact + retry and
        the retry's answer is delivered; the recovery round is loop plumbing,
        not a user-visible failure."""
        llm = FakeLLM(
            [
                LLMReply(text="(context window exceeded)", degraded=True, overflow=True),
                LLMReply(text="恢复后完成"),
            ]
        )
        messages = [
            {"role": "system", "content": "系统提示"},
            {"role": "user", "content": "开场" * 5000},
        ]
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=None,
            messages=messages,
            limits=ModeLimits(),
            compress_budget=500,
        )
        assert result == "恢复后完成"
        # The retry saw the emergency-truncated transcript: the huge user entry
        # is capped and marked instead of resending thousands of characters
        retried = llm.calls[1]["messages"]
        user_msg = next(m for m in retried if m.get("role") == "user")
        assert "上下文溢出截断" in user_msg["content"]
        assert len(user_msg["content"]) < 300

    async def test_second_overflow_ends_turn_with_actionable_text(self) -> None:
        llm = FakeLLM(
            [
                LLMReply(text="x", degraded=True, overflow=True),
                LLMReply(text="y", degraded=True, overflow=True),
            ]
        )
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=None,
            messages=_msgs(),
            limits=ModeLimits(),
            compress_budget=100,
        )
        assert result.startswith("[中断]")
        assert "compress_budget" in result

    async def test_readonly_batch_runs_in_parallel(self) -> None:
        """Two concurrent-safe calls in one round overlap in time; results are
        back-filled in call order."""
        overlaps: list[str] = []
        running: set[str] = set()

        def make(name: str) -> AgentTool:
            async def slow_read() -> str:
                running.add(name)
                overlaps.append(f"enter:{name}:{len(running)}")
                await asyncio.sleep(0.15)
                running.discard(name)
                return f"{name}-done"

            return AgentTool(
                name=name,
                description="slow read",
                handler=slow_read,
                concurrent_safe=True,
            )

        belt = Toolbelt(
            {"read_a": make("read_a"), "read_b": make("read_b")},
            PolicyEngine(),
        )
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall("1", "read_a", {}),
                        ToolCall("2", "read_b", {}),
                    )
                ),
                LLMReply(text="完成"),
            ]
        )
        messages = _msgs()
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=belt, messages=messages, limits=ModeLimits()
        )
        assert result == "完成"
        # parallel: both entered before either exited
        assert any(e.split(":")[2] == "2" for e in overlaps)
        # back-fill keeps call order despite parallel execution
        tool_rows = [m for m in messages if m.get("role") == "tool"]
        assert [m["tool_call_id"] for m in tool_rows] == ["1", "2"]
        assert [m["content"] for m in tool_rows] == ["read_a-done", "read_b-done"]

    async def test_write_batch_stays_serial(self) -> None:
        """A batch containing a non-safe (write) tool runs strictly in order."""
        events: list[str] = []

        def make(name: str, safe: bool) -> AgentTool:
            async def work() -> str:
                events.append(f"start:{name}")
                await asyncio.sleep(0.05)
                events.append(f"end:{name}")
                return "ok"

            return AgentTool(name=name, description="w", handler=work, concurrent_safe=safe)

        belt = Toolbelt(
            {
                "read": make("read", True),
                "write": make("write", False),
            },
            PolicyEngine(),
        )
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall("1", "read", {}),
                        ToolCall("2", "write", {}),
                    )
                ),
                LLMReply(text="完成"),
            ]
        )
        result = await run_mode(
            Mode.REACT, llm=llm, toolbelt=belt, messages=_msgs(), limits=ModeLimits()
        )
        assert result == "完成"
        assert events == ["start:read", "end:read", "start:write", "end:write"]

    async def test_loop_trip_mid_batch_keeps_pairing(self) -> None:
        """A duplicate call tripping mid-batch executes only the prefix and
        leaves no result-less assistant declarations behind."""
        calls: list[str] = []

        async def echo_tool(x: str = "") -> str:
            calls.append(x)
            return f"echo:{x}"

        belt = Toolbelt(
            {
                "echo_tool": AgentTool(
                    name="echo_tool",
                    description="e",
                    handler=echo_tool,
                    concurrent_safe=True,
                )
            },
            PolicyEngine(),
        )
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall("1", "echo_tool", {"x": "a"}),
                        ToolCall("2", "echo_tool", {"x": "a"}),
                        ToolCall("3", "echo_tool", {"x": "a"}),  # 3rd identical -> first trip
                        ToolCall("4", "echo_tool", {"x": "b"}),
                    )
                ),
                # After the advisory nudge the window still holds two earlier
                # "a" calls, so the very next "a" trips again -> abort
                LLMReply(tool_calls=(ToolCall("5", "echo_tool", {"x": "a"}),)),
            ]
        )
        messages = _msgs()
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=belt,
            messages=messages,
            limits=ModeLimits(max_rounds=5, max_tool_calls=40),
        )
        # Two-level guard: the first trip injected an advisory nudge (round
        # continued); the second trip aborted
        assert result.startswith("[中断] 疑似死循环")
        # The batch tail behind the tripping call is dropped (b never ran), and
        # after the advisory the very next identical call trips again (the
        # tripping call itself was recorded), so the abort carries no results
        assert calls == ["a", "a"]
        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant", "tool", "tool", "user"]
        assert "[advisory]" in messages[4]["content"]
        assert [m["tool_call_id"] for m in messages[2:4]] == ["1", "2"]
        assert len(messages[1]["tool_calls"]) == 2  # entry matches executed prefix
