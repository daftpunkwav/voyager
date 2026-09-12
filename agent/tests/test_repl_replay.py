"""REPL /replay: run listing and step-trail rendering from the trajectory
projection, read-only (no re-execution)."""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply
from agent.repl import ReplSession


def _session(app) -> tuple[ReplSession, list[str]]:
    out: list[str] = []
    session = ReplSession(app, out=out.append)
    return session, out


class TestReplay:
    async def test_replay_lists_and_renders_run(self, tmp_path, settle) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM([LLMReply(text="hello there")]),
        )
        try:
            await app.master.handle_user_message("hi")
            await settle(app)
            app.trajectory.catch_up()
            session, out = _session(app)
            await session.submit("/replay")
            assert "recent runs" in "".join(out)
            run_id = app.trajectory.list_runs(limit=1)[0]["run_id"]
            out.clear()
            await session.submit(f"/replay {run_id[:10]}")
            text = "".join(out)
            # Conversational runs stay alive between turns: status is running,
            # and the replay renders the llm step trail read-only
            assert "running" in text and "2 steps" in text
            assert "[llm] round-1" in text
        finally:
            app.close()

    async def test_replay_unknown_run(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            session, out = _session(app)
            await session.submit("/replay ghost")
            assert "[no run matching ghost]" in "".join(out)
            await session.submit("/replay")
            assert "no recorded runs" in "".join(out)
        finally:
            app.close()
