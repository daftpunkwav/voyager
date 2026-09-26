"""Domain capability REST surface: agent and human invoke the same
capability with the same standing."""

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


from platform_contracts import (
    ServiceError,
)


class TestSessionSurface:
    async def test_session_capability_shares_manager_with_tool(self, app) -> None:
        """The human path (capability) and the agent path (session tool) drive
        the same SessionManager: a session created via the capability is
        immediately visible through the tool surface."""
        from agent.tools import session_tools

        created = await execute(
            app.registry, "session", USER_CTX, {"action": "create", "title": "能力建的"}
        )
        sid = created["session_id"]
        assert "session" in app.spawner._toolbelt.names()
        listing = await execute(app.registry, "session", USER_CTX, {"action": "list"})
        assert any(r["session_id"] == sid and r["title"] == "能力建的" for r in listing["sessions"])
        tool = session_tools(app.registry, app.master.sessions)["session"]
        rows = await tool.handler(action="list")
        assert any(r["session_id"] == sid for r in rows["sessions"])

    async def test_set_active_and_get_session(self, app) -> None:
        created = await execute(app.registry, "session", USER_CTX, {"action": "create"})
        sid = created["session_id"]
        await execute(
            app.registry, "session", USER_CTX, {"action": "set_active", "session_id": sid}
        )
        listing = await execute(app.registry, "session", USER_CTX, {"action": "list"})
        assert listing["active"] == sid
        detail = await execute(
            app.registry, "session", USER_CTX, {"action": "get", "session_id": sid}
        )
        assert detail["found"] is True
        assert detail["history"] == []

    async def test_delete_session_refuses_unknown(self, app) -> None:
        with pytest.raises(ServiceError):
            await execute(
                app.registry, "session", USER_CTX, {"action": "delete", "session_id": "nope"}
            )

    async def test_compact_context_skips_small_context(self, app) -> None:
        out = await execute(app.registry, "context", USER_CTX, {"action": "compact"})
        assert out["mode"] == "skipped"

    async def test_context_status_reports_window(self, app, settle) -> None:
        from agent.runtime.state import RunStatus

        await app.master.handle_user_message("hello")
        await settle(app)
        app.master.chat.state.status = RunStatus.WAITING_INPUT
        out = await execute(app.registry, "context", USER_CTX, {"action": "status"})
        assert out["window_tokens"] > 0
        assert "used_pct" in out
