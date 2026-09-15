"""Turn close-out message kinds: degraded LLM text is marked error so the
chat UI renders it distinctly instead of masquerading as a normal answer.
"""

import asyncio

from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply
from platform_contracts import DomainEvent


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
