"""Turn close-out message kinds: degraded LLM text is marked error so the
chat UI renders it distinctly instead of masquerading as a normal answer,
and a degraded task turn lands FAILED instead of a fake completion.
"""

import asyncio

from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply
from agent.policy import PolicyEngine
from agent.runtime.state import RunState, RunStatus
from agent.subagent.instance import SubagentInstance, TaskBook
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
