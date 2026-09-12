"""Tests for the standalone REPL: event rendering, input routing
(chat vs pending ask), slash commands, and standalone LLM selection.
"""

import asyncio
from types import SimpleNamespace
from typing import Any

from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.llm_http import HttpLLM
from agent.main import build_agent
from agent.repl import ReplSession, _coerce_answer, _standalone_llm
from platform_contracts import ActorKind, ActorRef, DomainEvent, Event

_AGENT_ACTOR = ActorRef(kind=ActorKind.AGENT, id="agent.repl")


def _app(tmp_path, llm):
    return build_agent(
        data_dir=tmp_path / "rd",
        workspace_dir=tmp_path / "ws",
        llm=llm,
    )


class _Collector:
    """Render sink collecting strings so assertions can scan the transcript."""

    def __init__(self) -> None:
        self.chunks: list[str] = []

    def __call__(self, text: str) -> None:
        self.chunks.append(text)

    def text(self) -> str:
        return "".join(self.chunks)


async def _wait_for(collector: _Collector, needle: str, *, attempts: int = 300) -> None:
    for _ in range(attempts):
        if needle in collector.text():
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"expected {needle!r} in transcript, got: {collector.text()!r}")


async def test_chat_round_renders_reply(tmp_path, settle) -> None:
    app = _app(tmp_path, FakeLLM([LLMReply(text="你好呀")]))
    out = _Collector()
    session = ReplSession(app, out=out)
    session.start()
    try:
        assert await session.submit("嗨") is True
        await settle(app)
        await _wait_for(out, "agent> 你好呀")
    finally:
        await session.close()
        app.close()


async def test_ask_question_routes_next_line_as_answer(tmp_path, settle) -> None:
    llm = FakeLLM(
        [
            LLMReply(
                tool_calls=(
                    ToolCall(
                        "t1",
                        "ask_user",
                        {
                            "prompt": "用哪个颜色?",
                            "kind": "choice",
                            "options": ["红", "蓝"],
                        },
                    ),
                )
            ),
            LLMReply(text="好的,用红色。"),
        ]
    )
    app = _app(tmp_path, llm)
    out = _Collector()
    session = ReplSession(app, out=out)
    session.start()
    try:
        await session.submit("帮我选颜色")
        await _wait_for(out, "agent asks>")  # consumer task rendered the ask event
        await _wait_for(out, "(pick 1-2)")
        assert await session.submit("2") is True  # next line becomes the answer
        await settle(app)
        await _wait_for(out, "agent> 好的,用红色。")
        assert app.asker.pending_count == 0
    finally:
        await session.close()
        app.close()


async def test_slash_commands(tmp_path) -> None:
    app = _app(tmp_path, FakeLLM())
    out = _Collector()
    session = ReplSession(app, out=out)
    session.start()
    try:
        assert await session.submit("/help") is True
        assert "/todo" in out.text()
        assert await session.submit("/todo") is True
        assert "(todo list is empty)" in out.text()
        # session commands: listing, compacting (async handlers must run)
        assert await session.submit("/sessions") is True
        assert await session.submit("/session") is True
        assert await session.submit("/compact") is True
        assert "skipped" in out.text() or "压缩" in out.text()
        assert await session.submit("/nope") is True
        assert "unknown command" in out.text()
        assert await session.submit("/quit") is False
        assert await session.submit("/exit") is False
    finally:
        await session.close()
        app.close()


class _Settings:
    """Minimal SettingsReader stand-in: key lookups with an empty default."""

    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, key: str) -> str:
        return self._values.get(key, "")


async def test_standalone_llm_selection(tmp_path) -> None:
    # Configured endpoint -> HttpLLM; otherwise a self-explanatory FakeLLM.
    configured = _Settings(
        {
            "agent.llm.base_url": "http://x/v1",
            "agent.llm.model": "m",
            "agent.llm.api_key": "k",
            "agent.llm.timeout_s": "60",
        }
    )
    assert isinstance(_standalone_llm(configured), HttpLLM)
    assert not isinstance(_standalone_llm(_Settings({})), HttpLLM)


def test_coerce_answer_kinds() -> None:
    assert _coerce_answer("confirm", (), "Y") is True
    assert _coerce_answer("confirm", (), "随便") is False
    assert _coerce_answer("choice", ("红", "蓝"), "2") == "蓝"
    assert _coerce_answer("choice", ("红", "蓝"), "蓝") == "蓝"
    assert (
        _coerce_answer("choice", ("红", "蓝"), " nonsense ") == "红"
    )  # out of range: first option
    assert _coerce_answer("slider", (), "3.5") == 3.5
    assert _coerce_answer("slider", (), "abc") == 0.0
    assert _coerce_answer("text", (), "自由输入") == "自由输入"


def test_ask_event_contract_payload_keys() -> None:
    """REPL renders AGENT_ASK payloads; guard the keys it reads."""
    session_payload: dict[str, Any] = {
        "question_id": "abc",
        "prompt": "p",
        "kind": "confirm",
        "options": [],
        "min": None,
        "max": None,
    }
    out = _Collector()
    session = ReplSession(
        SimpleNamespace(  # type: ignore[arg-type]  # duck-typed: only .asker.answer is touched
            bus=SimpleNamespace(subscribe=lambda *p: None, unsubscribe=lambda s: None),
            asker=SimpleNamespace(answer=lambda qid, v: True),
            master=SimpleNamespace(handle_user_message=lambda t: asyncio.sleep(0)),
            registry=SimpleNamespace(get=lambda n: SimpleNamespace(handler=dict)),
        ),
        out=out,
    )
    session.render(Event(type=DomainEvent.AGENT_ASK, actor=_AGENT_ACTOR, payload=session_payload))
    assert "agent asks> p" in out.text()


async def test_bare_slash_does_not_crash(tmp_path) -> None:
    app = _app(tmp_path, FakeLLM())
    out = _Collector()
    session = ReplSession(app, out=out)
    session.start()
    try:
        assert await session.submit("/") is True
        assert "unknown command" in out.text()
    finally:
        await session.close()
        app.close()
