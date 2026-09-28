"""Turn close-out message kinds: degraded LLM text is marked error so the
chat UI renders it distinctly instead of masquerading as a normal answer,
and a degraded task turn lands FAILED instead of a fake completion.
"""

import asyncio

from agent.build import build_agent
from agent.engine.instance import SubagentInstance, TaskBook
from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.policy import PolicyEngine
from agent.runtime.state import RunState, RunStatus
from agent.tools import Toolbelt
from platform_contracts import DomainEvent, RuntimeEvent


def _message_kinds(app) -> list[str]:
    return [
        e.payload.get("kind", "message")
        for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])
    ]


async def _drive(app, text: str) -> None:
    await app.master.handle_user_message(text)
    while app.master._bg:
        await asyncio.gather(*list(app.master._bg))


def test_degraded_turn_marked_error(tmp_path) -> None:
    async def _down(messages, tools):
        return LLMReply(text="(LLM call failed: boom)", degraded=True)

    app = build_agent(
        data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(dynamic=_down)
    )
    try:
        asyncio.run(_drive(app, "hi"))
        kinds = _message_kinds(app)
        assert kinds and kinds[-1] == "error"
    finally:
        app.close()


def test_recovered_turn_marked_message(tmp_path) -> None:
    """One degraded round followed by a genuine answer: the delivered text
    is real, so the message stays a normal one."""
    llm = FakeLLM(
        [
            LLMReply(text="(LLM call failed: blip)", degraded=True),
            LLMReply(text="all good"),
        ]
    )
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=llm)
    try:
        asyncio.run(_drive(app, "hi"))
        kinds = _message_kinds(app)
        assert kinds and kinds[-1] == "message"
    finally:
        app.close()


def test_normal_turn_marked_message(tmp_path) -> None:
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    try:
        asyncio.run(_drive(app, "hi"))
        kinds = _message_kinds(app)
        assert kinds and kinds[-1] == "message"
    finally:
        app.close()


def test_conversational_delivery_joins_lead_ins(tmp_path) -> None:
    """A chat turn whose first round streamed text and then called a tool
    delivers lead-in + final answer as ONE message (the final round only
    writes the continuation), and the model-facing history carries the flow
    once — no duplicated lead-in entry."""

    seen = {"n": 0}

    def _sequenced(_messages, _tools=None):
        seen["n"] += 1
        if seen["n"] == 1:
            return LLMReply(
                text="我先查一下 usage。",
                tool_calls=(ToolCall(id="t1", name="read", arguments={"path": "x"}),),
            )
        return LLMReply(text="查完了,结果是这样。")

    app = build_agent(
        data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(dynamic=_sequenced)
    )
    try:
        asyncio.run(_drive(app, "hi"))
        full = "我先查一下 usage。\n\n查完了,结果是这样。"
        messages = [e.payload for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])]
        assert messages[-1]["content"] == full
        chat = app.master.chat
        assert chat is not None
        history = [m.get("content", "") for m in chat.history if m.get("role") == "assistant"]
        assert history == [full]  # the lead-in is carried once, by the closing
    finally:
        app.close()


def test_rounds_cap_winddown_marked_warning(tmp_path) -> None:
    """A rounds-cap wind-down ([中断] ...) is the caps speaking, not the
    model: the message carries kind=warning so the UI renders it as a system
    note instead of a Lucien answer bubble."""

    def _tool_loop(_messages, _tools=None):
        # A tool call every round: the loop only ends at the rounds cap
        return LLMReply(
            tool_calls=(ToolCall(id="t1", name="read", arguments={"path": "x"}),),
        )

    app = build_agent(
        data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(dynamic=_tool_loop)
    )
    try:

        async def _drive_capped() -> None:
            from platform_contracts import LOCAL_USER

            await app.settings.set("agent.rounds.max", 1, LOCAL_USER)
            await _drive(app, "go")

        asyncio.run(_drive_capped())
        kinds = _message_kinds(app)
        assert kinds and kinds[-1] == "warning"
        messages = [e.payload for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])]
        assert messages[-1]["content"].startswith("[中断]")
    finally:
        app.close()


class _RecordingEvents:
    """Minimal event stub: records emitted (type, payload) pairs."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict]] = []

    async def emit(self, type_, **payload) -> int:
        self.emitted.append((type_, payload))
        return 0


def test_degraded_task_turn_fails_instead_of_completing() -> None:
    """A task turn that ended on a degraded placeholder (quota / provider
    failure) instead of a model answer: it must land FAILED with the degraded
    text as the error and emit RunFailed - wait_subagent callers must see the
    failure, not a completed result that never materialized."""

    async def _down(_messages, _tools=None):
        return LLMReply(text="(LLM call failed: quota)", degraded=True)

    events = _RecordingEvents()
    inst = SubagentInstance(
        # Default REACT: the llm round step carries the degraded detail that
        # _turn_degraded reads back (DIRECT records it on events only)
        task=TaskBook(goal="g"),
        toolbelt=Toolbelt({}, PolicyEngine()),
        llm=FakeLLM(dynamic=_down),
        system_prompt="s",
        events=events,  # type: ignore[arg-type]  # duck-typed event stub
        state=RunState(task="g"),
    )
    result = asyncio.run(inst.run_turn("do it"))
    assert inst.state.status is RunStatus.FAILED
    assert inst.state.error == result == "(LLM call failed: quota)"
    failed = [p for t, p in events.emitted if t == RuntimeEvent.RUN_FAILED]
    assert failed and "quota" in failed[0]["error"]


def test_normal_task_turn_completes() -> None:
    """A genuine task reply keeps the COMPLETED contract: the degraded branch
    above must not swallow healthy runs."""
    events = _RecordingEvents()
    inst = SubagentInstance(
        task=TaskBook(goal="g"),
        toolbelt=Toolbelt({}, PolicyEngine()),
        llm=FakeLLM([LLMReply(text="done")]),
        system_prompt="s",
        events=events,  # type: ignore[arg-type]  # duck-typed event stub
        state=RunState(task="g"),
    )
    assert asyncio.run(inst.run_turn("do it")) == "done"
    assert inst.state.status is RunStatus.COMPLETED
    assert not [1 for t, _ in events.emitted if t == RuntimeEvent.RUN_FAILED]


class _SummarizingGovernor:
    """One-shot compaction stub: replaces the transcript the way the editor
    does (a SUMMARY_MARK row stands in for the condensed span) so run_turn's
    history write-back branch executes."""

    def __init__(self) -> None:
        self.armed = True

    async def enforce(self, messages: list[dict]) -> dict | None:
        if not self.armed:
            return None
        self.armed = False
        messages[:] = [
            messages[0],
            {"role": "user", "content": "[历史压缩]\n更早的轮次已压缩为摘要。"},
            *messages[2:],
        ]
        return {"mode": "llm"}

    def target_tokens(self) -> int:
        return 1000

    async def compact(self, messages: list[dict], target: int | None = None) -> None:
        return None


def test_compaction_writeback_keeps_substring_but_unequal_entries() -> None:
    """The compaction write-back dedup compares whole delivered segments, not
    substrings: an older assistant entry that merely appears inside the result
    ("回答" inside "新的回答") must survive the rebuild — containment matching
    would silently drop it from the model-facing history."""
    events = _RecordingEvents()
    inst = SubagentInstance(
        task=TaskBook(goal="g"),
        toolbelt=Toolbelt({}, PolicyEngine()),
        llm=FakeLLM(default="新的回答"),
        system_prompt="s",
        events=events,  # type: ignore[arg-type]  # duck-typed event stub
        state=RunState(task="g"),
    )
    inst.history.extend(
        [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "回答"},
        ]
    )
    inst.governor = lambda: _SummarizingGovernor()  # type: ignore[assignment,return-value]
    result = asyncio.run(inst.run_turn("q2"))
    assert result == "新的回答"
    assistant = [m["content"] for m in inst.history if m.get("role") == "assistant"]
    assert assistant == ["回答", "新的回答"]
