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


class TestMemorySurface:
    """Memory view/clear: data source for the settings page, without changing recall retrieval semantics."""

    async def test_get_memory_shape_and_profile(self, app) -> None:
        await execute(
            app.registry,
            "memory",
            USER_CTX,
            {"action": "remember", "key": "language", "value": "Chinese"},
        )
        out = await execute(app.registry, "memory", USER_CTX, {"action": "query"})
        assert set(out) == {
            "profile",
            "episodic",
            "semantic",
            "working",
            "retention_days",
            "purged_episodic",
            "purged_semantic",
            "vector_recall",
        }
        assert "language: Chinese" in out["profile"]["summary"]
        assert out["profile"]["items"] == [{"key": "language", "value": "Chinese"}]
        assert set(out["episodic"]) == {"recent", "shown"}
        assert out["episodic"]["shown"] == len(out["episodic"]["recent"])
        assert set(out["semantic"]) == {"recent", "shown"}
        assert set(out["working"]) == {"size"}
        assert isinstance(out["retention_days"], int)
        assert out["vector_recall"]["enabled"] is False  # standalone build: no embedder injected

    async def test_clear_memory_profile_empties_summary(self, app) -> None:
        await execute(
            app.registry, "memory", USER_CTX, {"action": "remember", "key": "k", "value": "v"}
        )
        out = await execute(
            app.registry, "memory", USER_CTX, {"action": "clear", "zone": "profile"}
        )
        assert out == {"zone": "profile", "cleared": {"profile": 1}}
        snapshot = await execute(app.registry, "memory", USER_CTX, {"action": "query"})
        assert snapshot["profile"]["summary"] == "(暂无用户画像)"
        assert snapshot["profile"]["items"] == []

    async def test_clear_memory_invalid_zone(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry, "memory", USER_CTX, {"action": "clear", "zone": "everything"}
            )
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    async def test_get_memory_retention_zero_does_not_purge(self, app) -> None:
        """retention_days=0 means agent-managed: the snapshot purges no episodic/semantic rows and purged_* are 0."""
        await execute(
            app.registry,
            "set_setting",
            USER_CTX,
            {"key": "agent.memory.retention_days", "value": 0},
        )
        app.memory.episodic.log("consider", "user is viewing langgraph")
        out = await execute(app.registry, "memory", USER_CTX, {"action": "query"})
        assert out["retention_days"] == 0
        assert out["purged_episodic"] == 0
        assert out["purged_semantic"] == 0
        assert out["episodic"]["shown"] == 1

    async def test_set_profile_empty_key_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry,
                "memory",
                USER_CTX,
                {"action": "remember", "key": "  ", "value": "x"},
            )
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    async def test_delete_profile_missing_key_is_noop(self, app) -> None:
        """A missing key is not an error (matching sqlite DELETE semantics)."""
        out = await execute(
            app.registry, "memory", USER_CTX, {"action": "forget", "key": "nonexistent"}
        )
        assert out == {"key": "nonexistent", "ok": True}


class TestRateTurn:
    async def test_rate_turn_stores_feedback_fact(self, app) -> None:
        out = await execute(
            app.registry,
            "rate_turn",
            USER_CTX,
            {"score": 4, "comment": "干得不错", "subject": "整理笔记"},
        )
        assert out["stored"] is True
        facts = app.memory.semantic.query(subject="整理笔记")
        assert any(f["relation"] == "评价" and "★★★★☆" in f["object"] for f in facts)

    async def test_rate_turn_rejects_non_integer_score(self, app) -> None:
        """bool is an int subclass and a float like 4.0 would pass the value
        check but crash the star rendering - both are rejected up front."""
        for bad in (4.5, 4.0, True, "4"):
            with pytest.raises(ServiceError):
                await execute(app.registry, "rate_turn", USER_CTX, {"score": bad})

    async def test_rate_turn_caps_comment_length(self, app) -> None:
        out = await execute(
            app.registry, "rate_turn", USER_CTX, {"score": 3, "comment": "长" * 5000}
        )
        assert out["stored"] is True
        facts = app.memory.semantic.query(relation="评价")
        assert facts
        assert all(len(f["object"]) <= 500 for f in facts)
