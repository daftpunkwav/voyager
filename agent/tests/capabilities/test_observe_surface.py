"""Domain capability REST surface: agent and human invoke the same
capability with the same standing."""

import asyncio

import pytest
from agent.llm import FakeLLM
from agent.main import build_agent
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ActorKind, ActorRef

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


@pytest.fixture()
def app(tmp_path):
    app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
    yield app
    app.memory.close()


class TestSurface:
    async def test_list_skills_and_read(self, app) -> None:
        index = await execute(app.registry, "list_skills", USER_CTX, {})
        names = {s["name"] for s in index}
        assert "explore-repo" in names  # built-in skill indexed
        doc = await execute(
            app.registry,
            "skill",
            USER_CTX,
            {"action": "load", "name": "explore-repo"},
        )
        assert doc["name"] == "explore-repo" and doc["text"]

    async def test_report_page_context(self, app) -> None:
        await execute(
            app.registry,
            "report_page_context",
            USER_CTX,
            {"page": "notes", "summary": "36 notes", "counts": {"notes": 36}},
        )
        assert app.pages.current().page == "notes"
        assert "notes=36" in app.pages.render()

    async def test_answer_question_roundtrip(self, app) -> None:
        from agent.tools.interact.question_broker import Question

        task = asyncio.create_task(app.asker.ask(Question(prompt="Continue?")))
        await asyncio.sleep(0.01)
        qid = next(iter(app.asker._pending))  # grab the id of the pending question for the test
        out = await execute(
            app.registry,
            "answer_question",
            USER_CTX,
            {"question_id": qid, "value": True},
        )
        assert out["matched"] is True
        assert await task is True

    async def test_list_subagents_shape(self, app) -> None:
        out = await execute(app.registry, "subagent", USER_CTX, {"action": "list"})
        assert set(out) == {"definitions", "running"}
        assert isinstance(out["definitions"], list)

    async def test_list_subagents_running_has_last_step(self, app, tmp_path) -> None:
        """running entries carry last_step; non-empty when a tool step exists."""
        from agent.llm import FakeLLM, LLMReply, ToolCall

        app2 = build_agent(
            data_dir=tmp_path / "rd2",
            workspace_dir=tmp_path / "ws2",
            llm=FakeLLM(
                [
                    LLMReply(tool_calls=(ToolCall("1", "glob", {"pattern": "*"}),)),
                    LLMReply(text="Done."),
                ]
            ),
        )
        try:
            await app2.master.handle_user_message("look at the directory")

            async def _chat_has_step() -> bool:
                out = await execute(app2.registry, "subagent", USER_CTX, {"action": "list"})
                chat = next((r for r in out["running"] if r["name"] == "chat"), None)
                return bool(chat and chat.get("last_step"))

            # the turn runs in the background: poll for a step trail instead of
            # a fixed sleep (load-dependent scheduling)
            deadline = asyncio.get_running_loop().time() + 3.0
            while not await _chat_has_step():
                assert asyncio.get_running_loop().time() < deadline, "no step trail yet"
                await asyncio.sleep(0.01)
            out = await execute(app2.registry, "subagent", USER_CTX, {"action": "list"})
            running = out["running"]
            assert running
            for r in running:
                assert "last_step" in r
                assert r["last_step"] is not None
                # Panel routing key: the chat session the run belongs to
                assert "session" in r
            chat = next((r for r in running if r["name"] == "chat"), None)
            assert chat is not None
            # A conversational instance is a chat session itself: never session-less
            assert chat["session"]
            # glob is in the step trail; the final last_step may be the final reply — either it or normal text is fine
            assert chat["last_step"]
            assert len(chat["last_step"]) <= 120
        finally:
            app2.memory.close()
