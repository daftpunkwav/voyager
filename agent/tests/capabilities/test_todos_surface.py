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
    ErrorSuffix,
    ServiceError,
)


class TestTodos:
    async def test_todowrite_query_reads_shared_store(self, app, tmp_path) -> None:
        """The plan panel's data source: the capability reads the same
        workspace/todo.json the LLM todowrite tool writes."""
        result = await execute(app.registry, "todowrite", USER_CTX, {})
        assert result == {"items": [], "done": 0, "total": 0}

        from agent.tools.workspace import TodoStore

        TodoStore(tmp_path / "ws" / "todo.json").replace(
            [
                {"content": "step one", "status": "done"},
                {"content": "step two", "status": "in_progress"},
            ]
        )
        result = await execute(app.registry, "todowrite", USER_CTX, {})
        assert result["total"] == 2 and result["done"] == 1
        assert [it["content"] for it in result["items"]] == ["step one", "step two"]

    async def test_todowrite_session_scoped(self, app, tmp_path) -> None:
        """Passing the open session's id addresses that session's plan file,
        not the shared global one (parallel sessions never overwrite each other)."""
        from agent.tools.workspace import TodoStore

        TodoStore(tmp_path / "ws" / "todo.json").replace([{"content": "global"}])
        TodoStore(tmp_path / "ws" / "todos" / "sess-a.json").replace([{"content": "session plan"}])
        result = await execute(app.registry, "todowrite", USER_CTX, {"session": "sess-a"})
        assert [it["content"] for it in result["items"]] == ["session plan"]
        legacy = await execute(app.registry, "todowrite", USER_CTX, {})
        assert [it["content"] for it in legacy["items"]] == ["global"]

    async def test_todowrite_rejects_illegal_session(self, app) -> None:
        """Session ids become file names; traversal shapes are fail-closed."""
        with pytest.raises(ServiceError) as ei:
            await execute(app.registry, "todowrite", USER_CTX, {"session": "../x"})
        assert ei.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)

    async def test_todowrite_human_write_updates_and_deletes(self, app, tmp_path) -> None:
        """Same surface as the tool: the human may also update/delete through
        the action parameter (no read-only special case)."""
        from agent.tools.workspace import TodoStore

        TodoStore(tmp_path / "ws" / "todos" / "sess-b.json").replace(
            [{"content": "only", "status": "pending"}]
        )
        out = await execute(
            app.registry,
            "todowrite",
            USER_CTX,
            {"session": "sess-b", "action": "update", "index": 0, "status": "done"},
        )
        assert out["done"] == 1
        out = await execute(
            app.registry, "todowrite", USER_CTX, {"session": "sess-b", "action": "delete"}
        )
        assert out == {"items": [], "done": 0, "total": 0}
