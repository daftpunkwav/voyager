"""Tests for instance-level context accounting: the system entry
carries the per-turn usage status line, provider-reported input tokens from
step details anchor the tracker, and session ids ride the step/delta payloads.
"""

from agent.context.budgets import ContextBudget
from agent.engine.instance import SubagentInstance, TaskBook
from agent.llm import FakeLLM, LLMReply, ToolCall, Usage
from agent.policy import PolicyEngine
from agent.runtime.events import RuntimeEvents
from agent.runtime.state import RunState
from agent.tools import AgentTool, Toolbelt
from platform_contracts import DomainEvent
from platform_eventbus import EventBus, EventLog


def _instance(llm, log_path, **kw) -> SubagentInstance:
    async def echo(x: str = "") -> str:
        return f"echo:{x}"

    belt = Toolbelt(
        {"echo_tool": AgentTool(name="echo_tool", description="t", handler=echo)},
        PolicyEngine(),
    )
    log = EventLog(log_path)
    defaults = {
        "task": TaskBook(goal="demo"),
        "toolbelt": belt,
        "llm": llm,
        "system_prompt": "SYS",
        "events": RuntimeEvents(EventBus(log)),
        "state": RunState(task="demo"),
    }
    defaults.update(kw)
    return SubagentInstance(**defaults)


class TestStatusLineInjection:
    async def test_system_entry_carries_status_line(self, tmp_path) -> None:
        llm = FakeLLM([LLMReply(text="done")])
        inst = _instance(
            llm,
            tmp_path / "events.db",
            budget=ContextBudget(window_tokens=123_456, max_output_tokens=1_000),
        )
        await inst.run_turn("hello")
        system = llm.calls[0]["messages"][0]
        assert system["role"] == "system"
        assert system["content"].startswith("SYS")
        assert "123456" in system["content"]  # resolved window reaches the model
        assert "context(action=compact)" in system["content"]

    async def test_reported_usage_anchors_next_turn(self, tmp_path) -> None:
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(ToolCall("c1", "echo_tool", {"x": "a"}),),
                    usage=Usage(input_tokens=45_000, output_tokens=10),
                ),
                LLMReply(text="done", usage=Usage(input_tokens=44_900, output_tokens=5)),
            ]
        )
        inst = _instance(llm, tmp_path / "events.db")
        await inst.run_turn("hello")
        # Monotonic anchor: the larger earlier round stays the reference
        assert inst.usage.last_reported == 45_000

    async def test_session_rides_step_payload(self, tmp_path) -> None:
        llm = FakeLLM([LLMReply(text="done")])
        log_path = tmp_path / "events.db"
        inst = _instance(
            llm,
            log_path,
            task=TaskBook(goal="demo", session="sess0001"),
            events=RuntimeEvents(EventBus(EventLog(log_path))),
            name="chat",
        )
        await inst.run_turn("hello")
        log = EventLog(log_path)
        steps = [e for _, e in log.read_after(types=[DomainEvent.AGENT_STEP])]
        assert steps and all(s.payload.get("session") == "sess0001" for s in steps)
