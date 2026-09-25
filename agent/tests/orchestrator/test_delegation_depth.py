"""Delegation depth: monotonic under a running instance, capped by the
user_only max_depth setting, and mode errors fail loud with a hint."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from agent.orchestrator.wake_budget import WakeBudget  # noqa: F401  # sibling import sanity
from agent.runtime.current import current_instance
from platform_contracts import ServiceError


class _Settings:
    def __init__(self, values: dict | None = None) -> None:
        self.values = values or {}

    def get(self, key: str):
        return self.values.get(key)


def _dispatch_kwargs(**over):
    kw = {
        "master": SimpleNamespace(
            reply=lambda *a, **k: None,
            digests=SimpleNamespace(upsert=lambda inst: None),
            sessions=SimpleNamespace(active_id=lambda: "s1"),
            task_graph=None,
            track_background=lambda t: None,
            finish_task=lambda *a, **k: None,
        ),
        "spawner": None,
        "settings": _Settings({"agent.subagents.max_depth": 2}),
        "policy": None,
        "subagents": None,
        "hooks": None,
        "goal": "do the thing",
    }
    kw.update(over)
    return kw


def _capture_spawner(captured: list):
    class _Sp:
        def spawn(self, task, *, persona="", name=""):
            captured.append((task, persona, name))
            return SimpleNamespace(
                id="child-1",
                state=SimpleNamespace(delegation_depth=0),
                name=name,
                toolbelt=None,
                task=task,
            )

        async def start(self, inst):
            return "done"

    return _Sp()


async def test_depth_counts_from_running_parent_and_enforces_cap() -> None:
    from agent.orchestrator.dispatch import dispatch_task

    captured: list = []
    parent = SimpleNamespace(state=SimpleNamespace(delegation_depth=2))
    token = current_instance.set(parent)
    try:
        # depth 3 > cap 2 -> forbidden, with the setting named in the hint
        with pytest.raises(ServiceError) as exc:
            await dispatch_task(**_dispatch_kwargs(spawner=_capture_spawner(captured)))
        assert exc.value.body.code.endswith("FORBIDDEN")
        assert "agent.subagents.max_depth" in exc.value.body.hint
        assert captured == []
    finally:
        current_instance.reset(token)


async def test_depth_within_cap_stamps_child_state() -> None:
    from agent.orchestrator.dispatch import DeferredDispatch, dispatch_task

    captured: list = []
    parent = SimpleNamespace(state=SimpleNamespace(delegation_depth=1))
    token = current_instance.set(parent)
    try:
        inst = await dispatch_task(**_dispatch_kwargs(spawner=_capture_spawner(captured)))
        assert not isinstance(inst, DeferredDispatch)
        assert inst.state.delegation_depth == 2  # parent depth + 1
    finally:
        current_instance.reset(token)


async def test_depth_defaults_to_one_without_parent() -> None:
    from agent.orchestrator.dispatch import DeferredDispatch, dispatch_task

    captured: list = []
    token = current_instance.set(None)
    try:
        inst = await dispatch_task(**_dispatch_kwargs(spawner=_capture_spawner(captured)))
        assert not isinstance(inst, DeferredDispatch)
        assert inst.state.delegation_depth == 1
    finally:
        current_instance.reset(token)


async def test_unknown_mode_fails_loud_with_valid_list() -> None:
    from agent.orchestrator.dispatch import dispatch_task

    captured: list = []
    with pytest.raises(ServiceError) as exc:
        await dispatch_task(
            **_dispatch_kwargs(spawner=_capture_spawner(captured), mode="deep_thought")
        )
    assert "unknown mode" in exc.value.body.message
    assert "react" in exc.value.body.hint
    assert captured == []
