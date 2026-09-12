"""Tests for loop detection: signature normalization, sliding-window cycle
detection, and the _react breaker wiring.
"""

from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.policy import PolicyEngine
from agent.runtime.loop_detection import LoopDetector
from agent.subagent import Mode, ModeLimits, run_mode
from agent.tools import AgentTool, Toolbelt


class TestSignature:
    def test_key_order_insensitive(self) -> None:
        assert LoopDetector.signature("t", {"a": 1, "b": 2}) == LoopDetector.signature(
            "t", {"b": 2, "a": 1}
        )

    def test_name_and_value_sensitive(self) -> None:
        assert LoopDetector.signature("t", {"a": 1}) != LoopDetector.signature("u", {"a": 1})
        assert LoopDetector.signature("t", {"a": 1}) != LoopDetector.signature("t", {"a": 2})


class TestRecord:
    def test_threshold_hit_at_third_repeat(self) -> None:
        d = LoopDetector()
        assert d.record("t", {"x": 1}) is False
        assert d.record("t", {"x": 1}) is False
        assert d.record("t", {"x": 1}) is True  # third repeat hits the threshold

    def test_different_args_not_a_loop(self) -> None:
        """Same tool with different arguments is legitimate iteration and must not trip."""
        d = LoopDetector()
        for i in range(5):
            assert d.record("t", {"n": i}) is False

    def test_rejected_calls_still_count(self) -> None:
        """record() runs before execution, so a call that would later be refused
        by policy still participates in the pattern."""
        d = LoopDetector()
        d.record("write_file", {"path": "x"})
        d.record("write_file", {"path": "x"})
        assert d.record("write_file", {"path": "x"}) is True  # outcome unknown at record time

    def test_bookkeeping_calls_are_transparent(self) -> None:
        """Interleaved todo updates neither trip on themselves nor evict a real
        repetition pattern from the window (grep -> todo -> grep still counts)."""
        d = LoopDetector()
        d.record("grep", {"q": "x"})
        assert d.record("todo_write", {"items": []}) is False  # never stored, never trips
        d.record("grep", {"q": "x"})
        for i in range(4):  # four more would evict both greps from a 6-slot window if counted
            assert d.record("todo_write", {"items": [i]}) is False
        assert d.record("grep", {"q": "x"}) is True  # 3 greps still detected

    def test_window_slides_out_old_calls(self) -> None:
        d = LoopDetector(window=6, threshold=3)
        assert d.record("t", {"x": 1}) is False
        assert d.record("t", {"x": 1}) is False
        # Six distinct calls push both old signatures fully out of the window
        for i in range(6):
            assert d.record("t", {"n": i}) is False
        assert d.record("t", {"x": 1}) is False  # only 1 old signature remains in the window
        assert d.record("t", {"x": 1}) is False  # 2 repeats, below threshold
        assert d.record("t", {"x": 1}) is True  # 3 repeats hit the threshold


class TestReactWiring:
    async def test_react_breaks_on_loop(self) -> None:
        """Repeated identical calls to one tool: _react breaks early instead of burning the round/tool caps."""
        llm = FakeLLM(
            dynamic=lambda _m, _t: LLMReply(tool_calls=(ToolCall("1", "echo_tool", {"x": "same"}),))
        )

        async def echo_tool(x: str = "") -> str:
            return f"echo:{x}"

        belt = Toolbelt(
            {"echo_tool": AgentTool(name="echo_tool", description="echo", handler=echo_tool)},
            PolicyEngine(),
        )
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=belt,
            messages=[{"role": "user", "content": "task"}],
            limits=ModeLimits(),  # max_rounds=20 / max_tool_calls=40; the breaker must trip well before
        )
        assert "疑似死循环" in result
        assert "echo_tool" in result
        # The breaker trips at the third repeat, far below the 40-tool-call cap
        assert len(llm.calls) < 10

    async def test_interrupted_transcript_keeps_pairs(self) -> None:
        """After the breaker fires, the transcript keeps no call-without-result rows (endpoint 400 protection)."""
        llm = FakeLLM(
            dynamic=lambda _m, _t: LLMReply(tool_calls=(ToolCall("1", "echo_tool", {"x": "same"}),))
        )

        async def echo_tool(x: str = "") -> str:
            return f"echo:{x}"

        belt = Toolbelt(
            {"echo_tool": AgentTool(name="echo_tool", description="echo", handler=echo_tool)},
            PolicyEngine(),
        )
        messages: list[dict] = [{"role": "user", "content": "task"}]
        await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=belt,
            messages=messages,
            limits=ModeLimits(),
        )
        for i, m in enumerate(messages):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                ids = [c["id"] for c in m["tool_calls"]]
                got = [
                    messages[j].get("tool_call_id")
                    for j in range(i + 1, len(messages))
                    if messages[j].get("role") == "tool"
                ][: len(ids)]
                assert len(got) == len(ids)

    async def test_first_call_loop_drops_assistant_line(self) -> None:
        """When the very first call trips, the whole assistant row is removed, leaving no empty tool_calls row."""
        # After two normal executions, the third round's call trips pre-execution:
        # rounds 1-2 each ran once; in round 3 the assistant row is enqueued but the call never runs -> removed whole
        calls = {"n": 0}

        async def dynamic(_messages, _tools=None):
            calls["n"] += 1
            return LLMReply(tool_calls=(ToolCall(str(calls["n"]), "echo_tool", {"x": "same"}),))

        llm = FakeLLM(dynamic=dynamic)

        async def echo_tool(x: str = "") -> str:
            return f"echo:{x}"

        belt = Toolbelt(
            {"echo_tool": AgentTool(name="echo_tool", description="echo", handler=echo_tool)},
            PolicyEngine(),
        )
        messages: list[dict] = [{"role": "user", "content": "task"}]
        result = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=belt,
            messages=messages,
            limits=ModeLimits(),
        )
        assert "疑似死循环" in result
        # No empty tool_calls declarations (a first-call trip removes the whole assistant row)
        assert all(m.get("role") != "assistant" or m.get("tool_calls") for m in messages)

    def test_nested_structure_key_order_insensitive(self) -> None:
        """Nested dict key order is irrelevant; list element order is significant (that is the semantics)."""
        a = LoopDetector.signature("t", {"m": [{"x": 1, "y": 2}], "q": "graph"})
        b = LoopDetector.signature("t", {"q": "graph", "m": [{"y": 2, "x": 1}]})
        assert a == b
        c = LoopDetector.signature("t", {"m": [{"y": 2, "x": 1}], "q": "graph", "n": [1, 2]})
        d = LoopDetector.signature("t", {"m": [{"y": 2, "x": 1}], "q": "graph", "n": [2, 1]})
        assert c != d
