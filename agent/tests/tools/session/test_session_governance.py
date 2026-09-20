"""Aggregated session tool: the agent surface refuses to touch the session
the user is looking at (rename/delete/set_active, interaction integrity),
while other sessions' lifecycle and the paged history read go through the
same one tool."""

from __future__ import annotations

import json

from agent.build import build_agent
from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.tools import Toolbelt


def _belt(app, *, confirm=None) -> Toolbelt:
    async def _yes(_prompt: str) -> bool:
        return True

    async def _noop(_msg: str) -> None:
        return None

    root = app.spawner._toolbelt
    return Toolbelt(dict(root._tools), root._policy, confirm=confirm or _yes, notify=_noop)


class TestActiveSessionProtection:
    async def test_active_session_is_protected(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            belt = _belt(app)
            active = app.master.sessions.active_id()
            out = await belt.call(
                ToolCall("1", "session", {"action": "rename", "session_id": active, "title": "x"})
            )
            assert out.startswith("[已拒绝]")
            out = await belt.call(
                ToolCall("2", "session", {"action": "delete", "session_id": active})
            )
            assert out.startswith("[已拒绝]")
            out = await belt.call(
                ToolCall("3", "session", {"action": "set_active", "session_id": active})
            )
            assert out.startswith("[已拒绝]")
        finally:
            app.close()

    async def test_other_session_can_be_renamed_and_deleted(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            belt = _belt(app)
            sid = app.master.sessions.create(title="side")["session_id"]
            out = await belt.call(
                ToolCall(
                    "1", "session", {"action": "rename", "session_id": sid, "title": "renamed"}
                )
            )
            assert "renamed" in out
            assert any(
                r["session_id"] == sid and r["title"] == "renamed"
                for r in app.master.sessions.list()
            )
            out = await belt.call(ToolCall("2", "session", {"action": "delete", "session_id": sid}))
            assert sid in out
            assert all(r["session_id"] != sid for r in app.master.sessions.list())
        finally:
            app.close()


class TestListAndRead:
    async def test_list_action_returns_sessions_and_active(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            sid = app.master.sessions.create(title="s")["session_id"]
            out = json.loads(await _belt(app).call(ToolCall("1", "session", {"action": "list"})))
            assert out["active"] == app.master.sessions.active_id()
            assert any(r["session_id"] == sid for r in out["sessions"])
        finally:
            app.close()

    async def test_pages_backward_with_cursor(self, tmp_path, settle) -> None:
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM([LLMReply(text="one"), LLMReply(text="two"), LLMReply(text="three")]),
        )
        try:
            for text in ("a", "b", "c"):
                await app.master.handle_user_message(text)
                await settle(app)
            belt = _belt(app)
            # Direct master calls publish no user.message rows; the agent
            # replies alone exercise the backward paging contract.
            page = json.loads(
                await belt.call(ToolCall("1", "session", {"action": "read", "limit": 2}))
            )
            assert page["has_more"] is True and len(page["messages"]) == 2
            newest = [m["text"] for m in page["messages"]]
            older = json.loads(
                await belt.call(
                    ToolCall(
                        "2",
                        "session",
                        {"action": "read", "limit": 10, "before_seq": page["oldest_seq"]},
                    )
                )
            )
            assert older["has_more"] is False
            texts = [m["text"] for m in older["messages"]]
            assert "one" in texts and not set(texts) & set(newest)
            assert all(m["seq"] < page["oldest_seq"] for m in older["messages"])
        finally:
            app.close()

    async def test_unknown_session_is_empty(self, tmp_path) -> None:
        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            out = await _belt(app).call(
                ToolCall("1", "session", {"action": "read", "session_id": "ghost"})
            )
            assert '"messages": []' in out
        finally:
            app.close()
