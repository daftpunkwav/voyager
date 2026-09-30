"""Tests for the LLM-facing context tool: status reads the executing
instance's window facts, compact restructures the live transcript through
the same editor engine the human path uses.
"""

import json

from agent.context.budgets import ContextBudget
from agent.engine.instance import SubagentInstance, TaskBook
from agent.llm import FakeLLM, LLMReply
from agent.policy import PolicyEngine
from agent.runtime.current import current_instance
from agent.runtime.events import RuntimeEvents
from agent.runtime.state import RunState
from agent.tools import AgentTool, Toolbelt, context_tools
from platform_eventbus import EventBus, EventLog


def _instance(llm, tmp_path) -> SubagentInstance:
    log_path = tmp_path / "events.db"

    async def echo(x: str = "") -> str:
        return f"echo:{x}"

    belt = Toolbelt(
        {"echo_tool": AgentTool(name="echo_tool", description="t", handler=echo)},
        PolicyEngine(),
    )
    return SubagentInstance(
        task=TaskBook(goal="demo"),
        toolbelt=belt,
        llm=llm,
        system_prompt="SYS",
        events=RuntimeEvents(EventBus(EventLog(log_path))),
        state=RunState(task="demo"),
        budget=ContextBudget(
            window_tokens=2_000,
            max_output_tokens=500,
            auto_compact_at=75,
            compact_target=200,
            compress_budget=150,
        ),
        history=[
            {"role": "user", "content": "word " * 600},
            {"role": "assistant", "content": "noted"},
        ],
    )


class TestContextTools:
    async def test_status_reads_instance_window(self, tmp_path) -> None:
        inst = _instance(FakeLLM(), tmp_path)
        tools = context_tools()
        token = current_instance.set(inst)
        try:
            outcome = await tools["context"].handler(action="status")
        finally:
            current_instance.reset(token)
        assert outcome["window_tokens"] == 2_000
        assert outcome["used_tokens"] > 0
        assert outcome["auto_compact_at_pct"] == 75

    async def test_compact_restructures_live_history(self, tmp_path) -> None:
        plan = json.dumps({"keep": [1], "summarize": [], "drop": [0], "summary": ""})
        inst = _instance(FakeLLM([LLMReply(text=plan)]), tmp_path)
        tools = context_tools()
        token = current_instance.set(inst)
        try:
            outcome = await tools["context"].handler(action="compact")
        finally:
            current_instance.reset(token)
        assert outcome["mode"] == "plan"
        assert inst.history == [{"role": "assistant", "content": "noted"}]

    async def test_compact_reports_fallback(self, tmp_path) -> None:
        """Mid-turn (live wire view) a failed plan falls back to the
        deterministic compress: the transcript is transient and rebuilt from
        history next turn."""
        inst = _instance(FakeLLM([LLMReply(text="not json")]), tmp_path)
        inst._turn_messages = [*inst.history]  # live view: the mid-turn surface
        tools = context_tools()
        token = current_instance.set(inst)
        try:
            outcome = await tools["context"].handler(action="compact")
        finally:
            current_instance.reset(token)
        assert outcome["mode"] == "fallback"

    async def test_compact_on_history_never_blind_truncates(self, tmp_path) -> None:
        """No live turn: the view is the PERSISTED history. A failed plan must
        leave it untouched (mode=skipped) — the mechanical fallback would drop
        the oldest entries permanently, with no summary row and no rebuild."""
        llm = FakeLLM([LLMReply(text="not json")])
        inst = _instance(llm, tmp_path)
        tools = context_tools()
        token = current_instance.set(inst)
        try:
            outcome = await tools["context"].handler(action="compact")
        finally:
            current_instance.reset(token)
        assert outcome["mode"] == "skipped"
        assert outcome["after_tokens"] == outcome["before_tokens"]
        assert inst.history == [
            {"role": "user", "content": "word " * 600},
            {"role": "assistant", "content": "noted"},
        ]
        assert llm.calls  # the planner was still attempted

    async def test_without_instance_returns_error(self) -> None:
        tools = context_tools()
        assert "error" in await tools["context"].handler(action="status")
        assert "error" in await tools["context"].handler(action="compact")
