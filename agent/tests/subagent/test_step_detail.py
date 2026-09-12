"""Tests for structured step details: tool steps carry call id /
arguments / outcome / latency, llm steps carry round / usage / latency, and
the transcript text stays identical to the plain-call path.
"""

from agent.llm import FakeLLM, LLMReply, ToolCall, Usage
from agent.policy import FsPolicy, PolicyEngine
from agent.runtime.state import RunState
from agent.subagent import Mode, ModeLimits
from agent.subagent.modes import run_mode
from agent.tools import Toolbelt, ensure_workdir, fs_tools


def _belt(root, **kw) -> Toolbelt:
    return Toolbelt(
        fs_tools([root]),
        PolicyEngine(fs=FsPolicy(roots=(str(root),))),
        **kw,
    )


def _collector():
    seen: list[tuple] = []

    async def on_step(kind: str, name: str, summary: str, detail: dict) -> None:
        seen.append((kind, name, summary, detail))

    return seen, on_step


class TestToolStepDetail:
    async def test_tool_detail_carries_call_facts(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        llm = FakeLLM(
            [
                LLMReply(tool_calls=(ToolCall("c-9", "list_dir", {"path": "."}),)),
                LLMReply(text="done"),
            ]
        )
        seen, on_step = _collector()
        text = await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(root),
            messages=[{"role": "user", "content": "look around"}],
            limits=ModeLimits(),
            on_step=on_step,
        )
        assert text == "done"
        tools = [s for s in seen if s[0] == "tool"]
        assert len(tools) == 1
        _kind, name, summary, detail = tools[0]
        assert name == "list_dir" and len(summary) <= 120
        assert detail["tool_call_id"] == "c-9"
        assert '"path"' in detail["args"] and detail["ok"] is True
        assert detail["ms"] >= 0 and detail["title"] == "list_dir"

    async def test_failed_call_detail_marks_not_ok(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        belt = _belt(root).trimmed(["read_file"])  # list_dir genuinely absent
        llm = FakeLLM(
            [
                LLMReply(tool_calls=(ToolCall("c-1", "list_dir", {"path": "."}),)),
                LLMReply(text="done"),
            ]
        )
        seen, on_step = _collector()
        await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=belt,
            messages=[{"role": "user", "content": "look around"}],
            limits=ModeLimits(),
            on_step=on_step,
        )
        tools = [s for s in seen if s[0] == "tool"]
        assert len(tools) == 1 and tools[0][3]["ok"] is False
        assert tools[0][3]["tool_call_id"] == "c-1"

    async def test_parallel_batch_details_share_batch_latency(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall("c-1", "list_dir", {"path": "."}),
                        ToolCall("c-2", "read_file", {"path": "nope.txt"}),
                    )
                ),
                LLMReply(text="done"),
            ]
        )
        seen, on_step = _collector()
        await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(root),
            messages=[{"role": "user", "content": "look around"}],
            limits=ModeLimits(),
            on_step=on_step,
        )
        tools = [s for s in seen if s[0] == "tool"]
        assert [t[3]["tool_call_id"] for t in tools] == ["c-1", "c-2"]
        assert all(t[3]["ms"] >= 0 for t in tools)

    async def test_long_args_capped_in_detail(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        big = "x" * 5000
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall("c-1", "write_file", {"path": "repo/b.txt", "content": big}),
                    )
                ),
                LLMReply(text="done"),
            ]
        )
        seen, on_step = _collector()

        async def yes(prompt: str) -> bool:
            return True

        await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(root, confirm=yes),
            messages=[{"role": "user", "content": "write it"}],
            limits=ModeLimits(),
            on_step=on_step,
        )
        tools = [s for s in seen if s[0] == "tool"]
        assert len(tools) == 1
        assert len(tools[0][3]["args"]) <= 2000 + len("…[截断]")


class TestLlmStepDetail:
    async def test_round_detail_carries_usage_and_latency(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(ToolCall("c-1", "list_dir", {"path": "."}),),
                    usage=Usage(input_tokens=120, output_tokens=30),
                ),
                LLMReply(text="done", usage=Usage(input_tokens=60, output_tokens=10)),
            ]
        )
        seen, on_step = _collector()
        await run_mode(
            Mode.REACT,
            llm=llm,
            toolbelt=_belt(root),
            messages=[{"role": "user", "content": "look around"}],
            limits=ModeLimits(),
            on_step=on_step,
        )
        rounds = [s for s in seen if s[0] == "llm" and s[1].startswith("round-")]
        assert len(rounds) == 2
        first = rounds[0][3]
        assert first["round"] == 1 and first["tool_calls"] == ["list_dir"]
        assert first["ms"] >= 0 and "ttft_ms" not in first  # FakeLLM does not stream
        assert (first["input_tokens"], first["output_tokens"]) == (120, 30)
        second = rounds[1][3]
        assert (second["input_tokens"], second["output_tokens"]) == (60, 10)


class TestStepPersistenceShape:
    def test_old_checkpoint_without_detail_still_loads(self) -> None:
        state = RunState.from_dict(
            {
                "task": "t",
                "status": "paused",
                "steps": [{"n": 1, "kind": "llm", "name": "round-1", "summary": "s", "ts": 1.0}],
            }
        )
        assert state.steps[0].detail == {}

    def test_detail_round_trips_through_dict(self) -> None:
        state = RunState(task="t")
        state.add_step("tool", "grep", "m", {"tool_call_id": "c-1", "ok": True})
        revived = RunState.from_dict(state.to_dict())
        assert revived.steps[0].detail == {"tool_call_id": "c-1", "ok": True}
