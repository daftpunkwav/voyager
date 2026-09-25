"""Team room: @-mention routing, member turns, and handoff delegation.

The chat session is a group chat among the resident team (Lucien speaks by
default): a mention hands the floor to a teammate, who runs one turn under
their own persona over the shared transcript and lands their reply attributed
to them (speaker on the agent.message payload and on the history entry).
"""

import asyncio

import pytest
from agent.build import build_agent
from agent.capabilities.deps import CapabilityDeps
from agent.capabilities.team.subagent import subagent_action
from agent.llm import FakeLLM, LLMReply
from agent.master.master import _parse_mention
from agent.personas import TEAM_KEYS, resolve_persona
from agent.runtime.state import RunStatus
from agent.subagent.turn import _transcript_view
from platform_capability import current_chat_session
from platform_contracts import DomainEvent, ServiceError


def _handoff_deps(handoff) -> CapabilityDeps:
    """CapabilityDeps with only team_handoff wired: the handoff action reads
    no other dependency, and unrelated fields would need a full app."""
    from agent.capabilities.deps import CapabilityDeps

    return CapabilityDeps(
        settings=None,  # type: ignore[arg-type]
        memory=None,  # type: ignore[arg-type]
        skills=None,  # type: ignore[arg-type]
        spawner=None,  # type: ignore[arg-type]
        subagents=None,  # type: ignore[arg-type]
        pages=None,  # type: ignore[arg-type]
        asker=None,  # type: ignore[arg-type]
        toolbelt=None,
        mcp=None,
        meter=None,
        checkpoints=None,
        plugins=None,
        user_hooks=None,
        todos=None,
        sessions=None,
        jobs=None,
        job_cancel=None,
        blackboard=None,
        team_handoff=handoff,
    )


def _messages(app) -> list[tuple[dict, dict]]:
    return [(e.payload, e.actor) for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])]


async def _drive(app, text: str, session: str = "") -> None:
    await app.master.handle_user_message(text, session_id=session)
    while app.master._bg:
        await asyncio.gather(*list(app.master._bg))


class TestParseMention:
    def test_display_name_and_alias_route(self) -> None:
        assert _parse_mention("@Elio 讲讲 real-mock") == ("explainer", "讲讲 real-mock")
        assert _parse_mention("@iris\n扫一下") == ("recon", "扫一下")
        assert _parse_mention("@miyai整理笔记") == ("organizer", "整理笔记")

    def test_bare_mention_stays_with_host(self) -> None:
        # a bare ping carries nothing to hand over: routing it would run a
        # member turn with no user message (an LLM request with no user role)
        assert _parse_mention("@Elio") == ("", "@Elio")
        assert _parse_mention("@Elio ") == ("", "@Elio ")

    def test_non_members_stay_with_host(self) -> None:
        # the host is the default addressee: an @lucien mention is ordinary speech
        assert _parse_mention("@lucien 你好") == ("", "@lucien 你好")
        # unknown names pass through verbatim (the host disambiguates)
        assert _parse_mention("@Stranger 帮忙") == ("", "@Stranger 帮忙")
        # a mention not at the head is content, not routing
        assert _parse_mention("让 @Elio 来讲") == ("", "让 @Elio 来讲")
        assert _parse_mention("普通消息") == ("", "普通消息")


class TestTranscriptView:
    def test_speaker_prefixed_and_consecutive_merged(self) -> None:
        out = _transcript_view(
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "host words"},
                {"role": "assistant", "content": "member words", "speaker": "explainer"},
                {"role": "assistant", "content": "more host"},
                {"role": "user", "content": "go on"},
            ]
        )
        assert [m["role"] for m in out] == ["user", "assistant", "user"]
        # host messages stay bare; the teammate's words carry their name
        assert out[1]["content"] == "host words\n\n【Elio】member words\n\nmore host"

    def test_unknown_speaker_falls_back_to_key(self) -> None:
        out = _transcript_view([{"role": "assistant", "content": "x", "speaker": "ghost"}])
        assert out[0]["content"] == "【ghost】x"


class TestSummaryWriteBack:
    """The compaction write-back: history is rebuilt from the wire view, where
    a teammate's speaker lives only as a 【display name】 prefix — the raw
    text + speaker key form must be restored, not lost."""

    @staticmethod
    def _inst(llm, history):
        from agent.policy import PolicyEngine
        from agent.runtime.events import RuntimeEvents
        from agent.runtime.state import RunState
        from agent.subagent import TaskBook
        from agent.subagent.instance import SubagentInstance
        from agent.tools import Toolbelt

        return SubagentInstance(
            task=TaskBook(goal="g"),
            toolbelt=Toolbelt({}, PolicyEngine()),
            llm=llm,
            system_prompt="sys",
            events=RuntimeEvents(None),
            state=RunState("g"),
            history=history,
        )

    def test_write_back_restores_member_speaker(self) -> None:
        llm = FakeLLM([LLMReply(text="done")])
        history = [
            {"role": "user", "content": "讲讲"},
            {"role": "assistant", "content": "member words", "speaker": "explainer"},
            {"role": "user", "content": "[历史压缩] 之前的讨论摘要"},
        ]
        inst = self._inst(llm, history)
        result = asyncio.run(inst.run_turn("继续"))
        assert result == "done"
        assert {
            "role": "assistant",
            "content": "member words",
            "speaker": "explainer",
        } in inst.history
        # the closing answer is the host's own words: bare, speaker-less
        assert inst.history[-1] == {"role": "assistant", "content": "done"}
        # history keeps raw text: no 【name】 prefix leaks back in (the view
        # re-prefixes on the next turn, exactly once)
        assert all("【" not in str(m.get("content", "")) for m in inst.history)


class TestMemberTurn:
    def test_team_keys_are_resident_personas(self) -> None:
        assert TEAM_KEYS == ("orchestrator", "recon", "explainer", "organizer", "graph_guide")
        for key in TEAM_KEYS:
            assert resolve_persona(key) is not None

    def test_mention_speaks_under_member_identity(self, tmp_path) -> None:
        seen: list[list[dict]] = []

        async def _spy(messages, tools=None):
            seen.append(messages)
            return LLMReply(text="我是 Elio,讲解导师。")

        app = build_agent(
            data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM(dynamic=_spy)
        )
        try:

            async def _scenario() -> None:
                await _drive(app, "@Elio 用一句话介绍自己")

            asyncio.run(_scenario())
            payload, _actor = _messages(app)[-1]
            # the reply is attributed to the member on the wire
            assert payload["speaker"] == "explainer"
            assert payload["content"] == "我是 Elio,讲解导师。"
            inst = app.master.sessions.instance_for(payload["session"])
            assert inst is not None
            # the group transcript records who spoke
            assert inst.history[-1]["speaker"] == "explainer"
            # the member's own persona layers drove the turn
            system = seen[-1][0]["content"]
            assert "Elio" in system and "explainer-mentor" in system
            # no member label leaks past the turn
            assert inst._member_label == ""
        finally:
            app.close()

    def test_plain_message_stays_unattributed(self, tmp_path) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM([LLMReply(text="host")]),
        )
        try:
            asyncio.run(_drive(app, "你好"))
            payload, _actor = _messages(app)[-1]
            assert "speaker" not in payload  # empty = Lucien, incl. pre-team history
            inst = app.master.sessions.instance_for(payload["session"])
            assert inst is not None
            assert "speaker" not in inst.history[-1]
        finally:
            app.close()


class TestHandoff:
    def _app(self, tmp_path):  # -> AgentApp (build_agent return is inference-friendly)
        return build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(
                [
                    LLMReply(text="host"),
                    LLMReply(
                        text="member answer",
                    ),
                ]
            ),
        )

    def test_handoff_rejects_non_member(self) -> None:
        async def _never(session, member, brief):  # pragma: no cover - must not run
            raise AssertionError("handoff must be rejected before dispatch")

        deps = _handoff_deps(_never)
        with pytest.raises(ServiceError):
            asyncio.run(subagent_action(deps, action="handoff", persona="stranger", message="x"))

    def test_queue_member_turn_runs_and_attributes(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:

            async def _scenario() -> None:
                await _drive(app, "先热个场")
                inst = app.master.sessions.instance_for(app.master.sessions.active_id())
                assert inst is not None
                out = await app.master.queue_member_turn(inst.session, "explainer", "讲一个概念")
                assert out == {
                    "member": "explainer",
                    "session": inst.session,
                    "queued": False,
                }
                while app.master._bg:
                    await asyncio.gather(*list(app.master._bg))
                payloads = [p for p, _ in _messages(app)]
                assert payloads[-1]["speaker"] == "explainer"
                assert inst.history[-1]["speaker"] == "explainer"

            asyncio.run(_scenario())
        finally:
            app.close()

    def test_handoff_while_running_parks_in_inbox(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:

            async def _scenario() -> None:
                await _drive(app, "热场")
                inst = app.master.sessions.instance_for(app.master.sessions.active_id())
                assert inst is not None
                inst.state.status = RunStatus.RUNNING
                out = await app.master.queue_member_turn(inst.session, "recon", "侦察一下")
                assert out["queued"] is True
                inbox = app.master._session_inbox(inst.session)
                assert inbox[-1].member == "recon" and inbox[-1].text == "侦察一下"

            asyncio.run(_scenario())
        finally:
            app.close()


class TestHandoffCapability:
    def test_handoff_capability_routes_and_validates(self, tmp_path, monkeypatch) -> None:
        calls: list[tuple[str, str, str]] = []

        async def _handoff(session, member, brief):
            calls.append((session, member, brief))
            return {"member": member, "session": session, "queued": False}

        deps = _handoff_deps(_handoff)
        token = current_chat_session.set("sess1")
        try:
            out = asyncio.run(
                subagent_action(deps, action="handoff", persona="Elio", message="讲讲 X")
            )
            result = out if isinstance(out, dict) else {}
            assert result.get("action") == "handoff" and result.get("queued") is False
            assert calls == [("sess1", "explainer", "讲讲 X")]
            with pytest.raises(ServiceError):
                asyncio.run(
                    subagent_action(deps, action="handoff", persona="orchestrator", message="x")
                )
            with pytest.raises(ServiceError):
                asyncio.run(subagent_action(deps, action="handoff", persona="elio", message="  "))
        finally:
            current_chat_session.reset(token)
