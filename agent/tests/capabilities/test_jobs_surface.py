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


class TestJobsSurface:
    """jobs action dispatch: list is the read-only projection; cancel/reorder
    route through host-injected routers — standalone (no router) they refuse
    with a readable UNAVAILABLE instead of a guess."""

    async def test_list_returns_projection(self, app) -> None:
        out = await execute(app.registry, "jobs", USER_CTX, {"action": "list"})
        assert isinstance(out, list)

    async def test_cancel_without_router_is_unavailable(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "jobs", USER_CTX, {"action": "cancel", "job_id": "j-1"})
        assert exc.value.body.code.endswith(ErrorSuffix.UNAVAILABLE.value)

    async def test_reorder_without_router_is_unavailable(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry,
                "jobs",
                USER_CTX,
                {"action": "reorder", "job_id": "j-1", "priority": 1},
            )
        assert exc.value.body.code.endswith(ErrorSuffix.UNAVAILABLE.value)

    async def test_unknown_action_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "jobs", USER_CTX, {"action": "purge"})
        assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)

    async def test_reorder_requires_priority_with_router_wired(self) -> None:
        """With a router wired, a missing priority is invalid input; a valid
        call routes (job_id, priority) through unchanged."""
        from types import SimpleNamespace
        from typing import cast

        from agent.capabilities.deps import CapabilityDeps
        from agent.capabilities.jobs.jobs import jobs_action

        calls: list[tuple[str, int]] = []

        async def _reorder(job_id: str, priority: int) -> dict:
            calls.append((job_id, priority))
            return {"job_id": job_id, "priority": priority}

        deps = cast(
            CapabilityDeps, SimpleNamespace(jobs=None, job_cancel=None, job_reorder=_reorder)
        )
        with pytest.raises(ServiceError) as exc:
            await jobs_action(deps, action="reorder", job_id="j-1")
        assert exc.value.body.code.endswith(ErrorSuffix.INVALID_INPUT.value)
        out = await jobs_action(deps, action="reorder", job_id="j-1", priority=7)
        assert out == {"job_id": "j-1", "priority": 7}
        assert calls == [("j-1", 7)]
