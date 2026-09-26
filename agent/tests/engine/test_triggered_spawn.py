"""Event-triggered subagent spawning: pattern extraction from definitions,
per-definition dispatch with goal/persona resolution, and the cooldown
frequency guard (settings-driven window, dirty values fall back).

Test type: unit (fakes for the registry and master's dispatch outlet).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agent.engine.registry import SubagentDef
from agent.engine.triggered_spawn import make_handler, trigger_patterns
from agent.settings import TRIGGERS_COOLDOWN_KEY
from platform_contracts import ErrorSuffix, ServiceError


def _def(name: str, trigger: str, description: str = "do the thing", persona: str = ""):
    return SubagentDef(name=name, description=description, persona=persona, trigger=trigger)


def _registry(defs: list):
    return SimpleNamespace(list=lambda: defs)


def _master():
    dispatched: list[tuple[str, dict]] = []

    async def dispatch_task(goal: str, **kw):
        dispatched.append((goal, kw))

    return SimpleNamespace(dispatch_task=dispatch_task), dispatched


def _settings(value):
    """Minimal SettingsReader; a raiser simulates a broken settings store."""
    if isinstance(value, Exception):

        def _raise(_key):
            raise value

        return SimpleNamespace(get=_raise)
    return SimpleNamespace(get=lambda _key: value)


class TestTriggerPatterns:
    def test_collects_event_triggers_deduped_in_order(self) -> None:
        registry = _registry(
            [
                _def("a", "event:task.*"),
                _def("b", "manual"),
                _def("c", "event:deploy.finished"),
                _def("d", "event:task.*"),  # duplicate pattern
            ]
        )
        assert trigger_patterns(registry) == ("task.*", "deploy.finished")

    def test_no_event_definitions_yields_empty(self) -> None:
        assert trigger_patterns(_registry([_def("a", "manual")])) == ()


class TestDispatch:
    async def test_matching_event_dispatches_one_instance_per_definition(self) -> None:
        master, dispatched = _master()
        registry = _registry(
            [
                _def("scout", "event:task.*", description="recon the task", persona=""),
                _def("named", "event:task.*", persona="elio"),
            ]
        )
        handler = make_handler(master, registry)
        await handler(SimpleNamespace(type="task.created"))
        # The persona passed to dispatch is the definition's name (its identity
        # in the roster), falling back to the persona preset key.
        assert [kw["persona"] for _g, kw in dispatched] == ["scout", "named"]
        assert all(g.startswith("[trigger task.created] ") for g, _kw in dispatched)

    async def test_non_matching_event_never_dispatches(self) -> None:
        master, dispatched = _master()
        handler = make_handler(master, _registry([_def("scout", "event:task.*")]))
        await handler(SimpleNamespace(type="deploy.finished"))
        assert dispatched == []

    async def test_pattern_match_is_case_sensitive_fnmatch(self) -> None:
        master, dispatched = _master()
        handler = make_handler(master, _registry([_def("scout", "event:task.*")]))
        await handler(SimpleNamespace(type="TASK.created"))
        assert dispatched == []

    async def test_one_failing_dispatch_does_not_break_the_rest(self) -> None:
        """A broken master for the first definition must not suppress the
        second definition's spawn: a failed trigger never breaks the loop."""

        calls: list[str] = []

        async def dispatch(goal: str, **kw):
            calls.append(goal)
            if len(calls) == 1:
                raise RuntimeError("dispatch exploded")

        master = SimpleNamespace(dispatch_task=dispatch)
        registry = _registry([_def("a", "event:x"), _def("b", "event:x")])
        await make_handler(master, registry)(SimpleNamespace(type="x"))
        assert len(calls) == 2


class TestCooldown:
    async def test_second_event_within_window_is_suppressed(self) -> None:
        master, dispatched = _master()
        handler = make_handler(
            master, _registry([_def("scout", "event:x")]), settings=_settings(300.0)
        )
        await handler(SimpleNamespace(type="x"))
        await handler(SimpleNamespace(type="x"))
        assert len(dispatched) == 1

    async def test_zero_window_disables_the_guard(self) -> None:
        master, dispatched = _master()
        handler = make_handler(master, _registry([_def("scout", "event:x")]), settings=_settings(0))
        await handler(SimpleNamespace(type="x"))
        await handler(SimpleNamespace(type="x"))
        assert len(dispatched) == 2

    async def test_cooldown_expires_after_the_window(self) -> None:
        master, dispatched = _master()
        handler = make_handler(master, _registry([_def("scout", "event:x")]), cooldown_s=0.02)
        await handler(SimpleNamespace(type="x"))
        await asyncio.sleep(0.03)
        await handler(SimpleNamespace(type="x"))
        assert len(dispatched) == 2

    async def test_cooldown_is_per_definition_and_pattern(self) -> None:
        master, dispatched = _master()
        registry = _registry([_def("a", "event:x"), _def("b", "event:x")])
        handler = make_handler(master, registry, settings=_settings(300.0))
        await handler(SimpleNamespace(type="x"))
        assert len(dispatched) == 2  # different defs: each fires once

    async def test_dirty_settings_value_falls_back_to_default_window(self) -> None:
        """A malformed cooldown setting falls back to the default window
        instead of raising into the event loop (guard stays on)."""
        master, dispatched = _master()
        handler = make_handler(
            master, _registry([_def("scout", "event:x")]), settings=_settings("not-a-number")
        )
        await handler(SimpleNamespace(type="x"))
        await handler(SimpleNamespace(type="x"))
        assert len(dispatched) == 1

    async def test_failing_settings_store_falls_back_to_default_window(self) -> None:
        master, dispatched = _master()
        handler = make_handler(
            master,
            _registry([_def("scout", "event:x")]),
            settings=_settings(ServiceError("settings", ErrorSuffix.UNAVAILABLE, "store down")),
        )
        await handler(SimpleNamespace(type="x"))
        await handler(SimpleNamespace(type="x"))
        assert len(dispatched) == 1

    async def test_key_matches_the_registered_settings_key(self) -> None:
        assert TRIGGERS_COOLDOWN_KEY == "agent.triggers.cooldown_s"
