"""Tests for hot-loading and hot-unloading user workspace/hooks.

Covers: the reload service (unloading only the user: prefix, reinstalling, selective
unsubscription, bad-file disclosure), the capability contract (USER-only, no path
parameter), coexistence with plugins/EventLoop (plugin subscriptions never mistakenly
withdrawn), and live-loop integration (after reload, same-process publish triggers). The
startup loading path is pinned by test_hooks.
"""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from agent.hooks import HookLoader, HookRegistry, UserHookReloader
from agent.llm import FakeLLM
from agent.main import build_agent
from agent.runtime import EventLoop
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import (
    LOCAL_USER,
    ActorKind,
    ActorRef,
    Event,
    ServiceError,
)
from platform_eventbus import EventBus, EventLog

USER_CTX = ActorContext(actor=LOCAL_USER)
AGENT_CTX = ActorContext(actor=ActorRef(kind=ActorKind.AGENT, id="agent.main", scopes=()))


async def _noop_hook(**kw: Any) -> None:
    """Async stand-in for a registered hook that is never fired in these tests."""


def _write_hook(hooks_dir: Path, name: str, data: dict) -> Path:
    hooks_dir.mkdir(parents=True, exist_ok=True)
    path = hooks_dir / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _reloader(
    tmp_path, *, registry: HookRegistry | None = None, plugins=None
) -> tuple[UserHookReloader, Path, HookRegistry]:
    """Returns the (reloader, hooks_dir, registry) triple; the directory is pinned to tmp_path/ws/hooks."""
    reg = registry if registry is not None else HookRegistry()
    hooks_dir = tmp_path / "ws" / "hooks"
    return UserHookReloader(reg, hooks_dir, plugins=plugins), hooks_dir, reg


def _make_plugin(root: Path, name: str = "example", *, enabled: bool = True) -> Path:
    """Minimal declarative plugin: one hook on note.created (no skill/MCP, enough to exercise the decision chain)."""
    d = root / name
    d.mkdir(parents=True)
    (d / "plugin.json").write_text(
        json.dumps(
            {
                "name": name,
                "version": "0.1.0",
                "description": "Test plugin",
                "permissions": {"scopes": [], "network": "off", "fs": "none"},
                "contains": {"skills": [], "hooks": ["hooks/on-note.json"], "mcp": None},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    hook_dir = d / "hooks"
    hook_dir.mkdir()
    (hook_dir / "on-note.json").write_text(
        json.dumps({"on": "note.created", "description": f"{name} hook", "enabled": enabled}),
        encoding="utf-8",
    )
    return d


class TestRegistryOwnership:
    """Pattern ownership records on HookRegistry."""

    def test_record_with_source_tracks_owners(self) -> None:
        hooks = HookRegistry()
        hooks.record_event_pattern("note.created", source="user:a")
        hooks.record_event_pattern("note.created", source="plugin:x:h")
        hooks.record_event_pattern("note.created", source="user:a")  # repeated: idempotent
        assert hooks.pattern_owner_sources("note.created") == ("plugin:x:h", "user:a")
        assert hooks.pattern_owner_sources("ghost.*") == ()

    def test_forget_clears_owners(self) -> None:
        hooks = HookRegistry()
        hooks.record_event_pattern("note.created", source="user:a")
        hooks.forget_event_pattern("note.created")
        assert hooks.event_patterns == ()
        assert hooks.pattern_owner_sources("note.created") == ()

    def test_remove_source_cleans_owners(self) -> None:
        """remove_source also drops ownership records under that prefix: once a side is unloaded its
        declaration no longer holds, and a ghost source would pin the keep decision for the other side.
        The subscription itself is kept (the pattern remains in event_patterns); actual unsubscription
        stays with the caller via an explicit forget."""
        hooks = HookRegistry()
        hooks.record_event_pattern("note.created", source="user:a")
        hooks.record_event_pattern("note.created", source="plugin:x:h")
        hooks.register("on_event", _noop_hook, source="user:a")
        assert hooks.remove_source("user:") == 1
        assert hooks.pattern_owner_sources("note.created") == ("plugin:x:h",)
        assert hooks.event_patterns == ("note.created",)

    def test_sources_lists_registered(self, tmp_path) -> None:
        hooks = HookRegistry()
        d = tmp_path / "hooks"
        d.mkdir()
        (d / "a.json").write_text(
            json.dumps({"on": "note.created", "enabled": True}), encoding="utf-8"
        )
        HookLoader(hooks).load_dir(d, source="user", approved=True)
        assert hooks.sources == ("user:a",)


class TestReloadService:
    """Reload service-level behavior (without build_agent)."""

    async def test_reload_loads_and_returns_shape(self, tmp_path) -> None:
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(
            hooks_dir,
            "note-watch.json",
            {"on": "note.created", "description": "note created", "enabled": True},
        )
        _write_hook(hooks_dir, "lifecycle.json", {"on": "on_user_message", "enabled": True})
        out = reloader.reload()
        assert out["loaded"] == 2
        assert out["event_patterns"] == [
            "note.created"
        ]  # lifecycle points never enter the subscription
        assert out["skipped"] == []
        assert reg.registered() == {"on_event": 1, "on_user_message": 1}
        assert "user:note-watch" in reg.sources

    async def test_reload_idempotent_no_duplicate(self, tmp_path) -> None:
        """load_dir first (simulating startup loading) then reload: unload before install, no duplicate registration."""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        HookLoader(reg).load_dir(hooks_dir, source="user", approved=True)
        out = reloader.reload()
        assert out["loaded"] == 1
        assert reg.registered() == {"on_event": 1}
        assert reg.event_patterns == ("note.created",)

    async def test_empty_dir_clears_user_hooks(self, tmp_path) -> None:
        """After emptying the directory, reload -> loaded=0, user hooks and subscriptions cleared, no crash."""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        HookLoader(reg).load_dir(hooks_dir, source="user", approved=True)
        (hooks_dir / "a.json").unlink()
        out = reloader.reload()
        assert out["loaded"] == 0
        assert out["event_patterns"] == []
        assert reg.registered() == {}

    async def test_missing_dir_succeeds_zero(self, tmp_path) -> None:
        """A missing directory counts as empty: returns loaded=0 successfully, creates no directory, no crash."""
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        out = reloader.reload()
        assert out == {"loaded": 0, "event_patterns": [], "skipped": []}
        assert not hooks_dir.exists()

    async def test_bad_json_skipped_and_disclosed(self, tmp_path) -> None:
        """A broken json file is skipped and disclosed individually; the rest load as usual (matching plugin loading tolerance)."""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "broken.json").write_text("{not json", encoding="utf-8")
        _write_hook(hooks_dir, "good.json", {"on": "note.created", "enabled": True})
        out = reloader.reload()
        assert out["loaded"] == 1
        assert len(out["skipped"]) == 1
        assert out["skipped"][0]["path"] == "broken.json"
        assert out["skipped"][0]["reason"]
        assert reg.registered() == {"on_event": 1}

    async def test_non_dict_json_skipped(self, tmp_path) -> None:
        """Non-object JSON such as arrays is skipped like a bad file, without breaking the reload."""
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "array.json").write_text("[1, 2]", encoding="utf-8")
        out = reloader.reload()
        assert out["loaded"] == 0
        assert [s["path"] for s in out["skipped"]] == ["array.json"]

    async def test_non_string_on_does_not_break_reload(self, tmp_path) -> None:
        """A non-string on is defensively rejected: the file is skipped (loaded=0), nothing enters
        event_patterns, skipped discloses the reason, and reload never crashes."""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "num.json").write_text(
            json.dumps({"on": 123, "enabled": True}), encoding="utf-8"
        )
        out = reloader.reload()
        assert out["loaded"] == 0
        assert [s["path"] for s in out["skipped"]] == ["num.json"]
        assert reg.event_patterns == ()  # non-string on never enters the subscription
        assert reg.registered() == {}
        (hooks_dir / "num.json").unlink()
        assert reloader.reload()["event_patterns"] == []

    async def test_star_on_skipped_and_disclosed(self, tmp_path) -> None:
        """A file with on: "*" is refused and shows up in skipped; reload neither crashes nor subscribes,
        and the remaining files load as usual."""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "star.json", {"on": "*", "enabled": True})
        _write_hook(hooks_dir, "good.json", {"on": "note.created", "enabled": True})
        out = reloader.reload()
        assert out["loaded"] == 1
        assert [s["path"] for s in out["skipped"]] == ["star.json"]
        assert out["skipped"][0]["reason"]
        assert "*" not in reg.event_patterns
        assert reg.registered() == {"on_event": 1}

    async def test_disabled_file_not_loaded(self, tmp_path) -> None:
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "off.json", {"on": "note.created", "enabled": False})
        out = reloader.reload()
        assert out["loaded"] == 0
        assert reg.event_patterns == ()
        assert reg.registered() == {}

    async def test_sync_called_with_latest_patterns(self, tmp_path) -> None:
        """reload converges subscriptions through the single injected sync callback; injection performs an initial baseline sync."""
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        seen: list[tuple[str, ...]] = []
        reloader.set_subscription_sync(seen.append)
        assert seen == [()]  # injection performs the baseline sync
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        assert seen[-1] == ("note.created",)

    async def test_lifecycle_hook_fires_after_reload(self, tmp_path, caplog) -> None:
        """After reload, lifecycle-point hooks fire immediately; they never enter event_patterns."""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "life.json", {"on": "on_user_message", "enabled": True})
        reloader.reload()
        with caplog.at_level(logging.INFO, logger="agent.hooks.loader"):
            await reg.fire("on_user_message", content="hi")
        assert sum("life" in r.message for r in caplog.records) == 1


class TestSelectiveForget:
    """Unsubscription only removes the user side; plugin subscriptions are never mistakenly withdrawn (layered decisions)."""

    async def test_user_only_pattern_forgotten_after_delete(self, tmp_path) -> None:
        reloader, hooks_dir, reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        out = reloader.reload()
        assert out["event_patterns"] == []
        assert "note.created" not in reg.event_patterns

    async def test_pattern_kept_while_other_user_file_declares(self, tmp_path) -> None:
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        _write_hook(hooks_dir, "b.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        out = reloader.reload()
        assert out["event_patterns"] == ["note.created"]  # b.json still declares it

    async def test_pattern_kept_for_plugin_owner(self, tmp_path) -> None:
        """Owner layer: while a plugin still declares the same pattern, deleting the user file does not unsubscribe."""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        reg.record_event_pattern("note.created", source="plugin:ex:hooks/on-note.json")
        reg.register("on_event", _noop_hook, source="plugin:ex:hooks/on-note.json")
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        out = reloader.reload()
        assert out["event_patterns"] == ["note.created"]  # the plugin remains, subscription kept
        assert reg.registered() == {"on_event": 1}  # what remains is the plugin registration

    async def test_unload_only_user_prefix(self, tmp_path) -> None:
        """Hot unload removes only the user: prefix; plugin and other prefixed registrations are untouched."""
        reloader, hooks_dir, reg = _reloader(tmp_path)
        reg.register("post_tool", _noop_hook, source="plugin:ex:h")
        reg.register("post_tool", _noop_hook, source="local")
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        reloader.reload()
        assert reg.registered() == {"post_tool": 2}  # plugin and local registrations both survive

    async def test_plugin_backup_keeps_pattern(self, tmp_path) -> None:
        """Plugin fallback layer: no owner record, but an approved plugin still wants the pattern -> the subscription is kept."""
        plugins = SimpleNamespace(pattern_still_wanted=lambda pattern: True)
        reloader, hooks_dir, _reg = _reloader(tmp_path, plugins=plugins)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        out = reloader.reload()
        assert out["event_patterns"] == ["note.created"]

    async def test_declared_plugin_backup_not_enough_when_nobody_needs(self, tmp_path) -> None:
        """Fallback says False and no owner -> withdrawn; no dangling subscriptions left behind."""
        plugins = SimpleNamespace(pattern_still_wanted=lambda pattern: False)
        reloader, hooks_dir, _reg = _reloader(tmp_path, plugins=plugins)
        _write_hook(hooks_dir, "a.json", {"on": "note.created", "enabled": True})
        reloader.reload()
        (hooks_dir / "a.json").unlink()
        assert reloader.reload()["event_patterns"] == []


class TestListService:
    """list_user_hooks is a read-only listing."""

    async def test_list_shape_and_loaded_flag(self, tmp_path) -> None:
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        _write_hook(
            hooks_dir, "on.json", {"on": "note.created", "description": "on-desc", "enabled": True}
        )
        _write_hook(hooks_dir, "off.json", {"on": "note.deleted", "enabled": False})
        reloader.reload()  # loads on.json only
        items = reloader.list()
        by_name = {i["path"]: i for i in items}
        assert set(by_name) == {"on.json", "off.json"}
        assert by_name["on.json"]["on"] == "note.created"
        assert by_name["on.json"]["enabled"] is True
        assert by_name["on.json"]["description"] == "on-desc"
        assert by_name["on.json"]["loaded"] is True
        assert by_name["off.json"]["loaded"] is False

    async def test_list_bad_file_zeroed(self, tmp_path) -> None:
        reloader, hooks_dir, _reg = _reloader(tmp_path)
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "bad.json").write_text("{oops", encoding="utf-8")
        (items,) = reloader.list()
        assert items["path"] == "bad.json"
        assert items["on"] == "" and items["enabled"] is False and items["loaded"] is False

    async def test_list_missing_dir_empty(self, tmp_path) -> None:
        reloader, _hooks_dir, _reg = _reloader(tmp_path)
        assert reloader.list() == []


class TestCapabilityContract:
    """Capability surface contract (through the full build_agent assembly)."""

    def _build(self, tmp_path):
        return build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())

    async def test_reload_contract_shape(self, tmp_path) -> None:
        app = self._build(tmp_path)
        try:
            _write_hook(
                tmp_path / "ws" / "hooks",
                "a.json",
                {"on": "note.created", "description": "u", "enabled": True},
            )
            out = await execute(
                app.registry,
                "extension",
                USER_CTX,
                {"kind": "hook", "action": "reload"},
            )
            assert out == {"loaded": 1, "event_patterns": ["note.created"], "skipped": []}
            assert "note.created" in app.loop.patterns  # subscription sync already applied
        finally:
            app.memory.close()

    async def test_agent_actor_may_reload(self, tmp_path) -> None:
        """Parity: the agent may trigger a reload (its tool side is L2-gated);
        the directory stays pinned, so no path can be smuggled in."""
        app = self._build(tmp_path)
        try:
            out = await execute(
                app.registry,
                "extension",
                AGENT_CTX,
                {"kind": "hook", "action": "reload"},
            )
            assert set(out) >= {"loaded", "event_patterns", "skipped"}
        finally:
            app.memory.close()

    async def test_no_actor_rejected(self, tmp_path) -> None:
        app = self._build(tmp_path)
        try:
            with pytest.raises(ServiceError) as exc:
                await execute(
                    app.registry,
                    "extension",
                    None,
                    {"kind": "hook", "action": "reload"},
                )
            assert exc.value.body.code == "CAPABILITY.AUTH_REQUIRED"
        finally:
            app.memory.close()

    async def test_no_path_parameter_accepted(self, tmp_path) -> None:
        """The hook reload action takes no path parameter: the hooks directory
        is pinned at assembly time, so no arbitrary-path loading channel
        exists (unknown kinds/actions are rejected by the dispatch)."""
        app = self._build(tmp_path)
        try:
            with pytest.raises(TypeError):
                await execute(
                    app.registry,
                    "extension",
                    USER_CTX,
                    {"kind": "hook", "action": "reload", "path": str(tmp_path / "elsewhere")},
                )
        finally:
            app.memory.close()

    async def test_list_user_hooks_contract(self, tmp_path) -> None:
        _write_hook(
            tmp_path / "ws" / "hooks",
            "a.json",
            {"on": "note.created", "description": "u", "enabled": True},
        )
        app = self._build(tmp_path)
        try:
            out = await execute(
                app.registry,
                "extension",
                USER_CTX,
                {"kind": "hook", "action": "list"},
            )
            assert out == {
                "items": [
                    {
                        "path": "a.json",
                        "on": "note.created",
                        "enabled": True,
                        "description": "u",
                        "loaded": True,
                    }
                ]
            }
        finally:
            app.memory.close()


def inspect_capability_params(app, name: str) -> set[str]:
    """Explicit parameter names of a capability handler (excluding the injected _actor)."""
    import inspect

    handler = app.registry.get(name).handler
    return {p for p in inspect.signature(handler).parameters if p != "_actor"}


# ---- Live-loop integration (build_agent + real EventLoop; changes take effect without restart) ----


async def _run_loop_task(loop: EventLoop):
    task = asyncio.create_task(loop.run())
    for _ in range(100):  # run() backfills before subscribing; wait for assembly
        if loop._sub is not None:
            break
        await asyncio.sleep(0)
    await asyncio.sleep(0)  # ensure it is blocked in sub.get
    return task


class TestLiveLoopIntegration:
    """Same process, no app rebuild: write a file -> reload -> publish triggers; delete the file -> reload unsubscribes."""

    async def _app_with_live_loop(self, tmp_path):
        bus = EventBus(EventLog(tmp_path / "events.db"))
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            plugins_dir=tmp_path / "plugins",
            bus=bus,
        )
        task = await _run_loop_task(app.loop)
        return app, bus, task

    async def test_write_reload_publish_triggers(self, tmp_path, caplog) -> None:
        """After reload, a same-process publish (note.created) really fires the user hook."""
        app, bus, task = await self._app_with_live_loop(tmp_path)
        try:
            assert "note.created" not in app.loop.patterns  # not subscribed before reload
            _write_hook(
                tmp_path / "ws" / "hooks",
                "u.json",
                {"on": "note.created", "description": "user observed", "enabled": True},
            )
            out = await execute(
                app.registry,
                "extension",
                USER_CTX,
                {"kind": "hook", "action": "reload"},
            )
            assert out["loaded"] == 1
            assert "note.created" in app.loop.patterns  # subscribed without a restart
            with caplog.at_level(logging.INFO, logger="agent.hooks.loader"):
                await bus.publish(Event(type="note.created", actor=LOCAL_USER, payload={}))
                await asyncio.sleep(0)
            assert sum("user observed" in r.message for r in caplog.records) == 1
        finally:
            app.loop.stop()
            task.cancel()
            app.log.close()  # the empty EventLog created inside build_agent (owns_log=False)
            app.memory.close()

    async def test_delete_reload_stops_trigger(self, tmp_path, caplog) -> None:
        """No plugin: delete the file -> reload -> a further publish no longer triggers; the subscription is withdrawn."""
        hooks_dir = tmp_path / "ws" / "hooks"
        _write_hook(
            hooks_dir,
            "u.json",
            {"on": "note.created", "description": "user observed", "enabled": True},
        )
        app, bus, task = await self._app_with_live_loop(tmp_path)
        try:
            assert "note.created" in app.loop.patterns  # subscribed by startup loading
            (hooks_dir / "u.json").unlink()
            await execute(
                app.registry,
                "extension",
                USER_CTX,
                {"kind": "hook", "action": "reload"},
            )
            assert "note.created" not in app.loop.patterns  # unsubscribed
            with caplog.at_level(logging.INFO, logger="agent.hooks.loader"):
                await bus.publish(Event(type="note.created", actor=LOCAL_USER, payload={}))
                await asyncio.sleep(0)
            assert caplog.records == []  # no longer triggered
        finally:
            app.loop.stop()
            task.cancel()
            app.log.close()
            app.memory.close()

    async def test_plugin_subscription_survives_user_reload(self, tmp_path, caplog) -> None:
        """With a plugin: the plugin approves note.created; adding/removing a user hook on the same pattern
        never disturbs the plugin across reloads — counts, sources, and the subscription all survive;
        only revoking the plugin unsubscribes."""
        _make_plugin(tmp_path / "plugins", "ex")
        app, _bus, task = await self._app_with_live_loop(tmp_path)
        try:
            # Approve the plugin -> subscription present, plugin hook present
            await execute(
                app.registry, "set_plugin_approval", USER_CTX, {"name": "ex", "approved": True}
            )
            assert "note.created" in app.loop.patterns
            plugin_sources = [s for s in app.hooks.sources if s.startswith("plugin:")]
            assert plugin_sources == ["plugin:ex:on-note"]  # source uses the file stem
            # User adds a hook on the same pattern -> reload: plugin registration and subscription unaffected
            _write_hook(
                tmp_path / "ws" / "hooks",
                "u.json",
                {"on": "note.created", "description": "user observed", "enabled": True},
            )
            await execute(
                app.registry,
                "extension",
                USER_CTX,
                {"kind": "hook", "action": "reload"},
            )
            assert app.hooks.registered() == {"on_event": 2}
            assert "note.created" in app.loop.patterns
            assert [s for s in app.hooks.sources if s.startswith("plugin:")] == plugin_sources
            # Delete the user file -> reload: the pattern is still kept because of the plugin
            (tmp_path / "ws" / "hooks" / "u.json").unlink()
            await execute(
                app.registry,
                "extension",
                USER_CTX,
                {"kind": "hook", "action": "reload"},
            )
            assert app.hooks.registered() == {"on_event": 1}
            assert "note.created" in app.loop.patterns
            # Revoke the plugin: with nobody wanting it, the pattern finally exits
            await execute(
                app.registry, "set_plugin_approval", USER_CTX, {"name": "ex", "approved": False}
            )
            assert "note.created" not in app.loop.patterns
            assert (
                caplog.records == []
            )  # nothing published in this case; all assertions above are state checks
        finally:
            app.loop.stop()
            task.cancel()
            app.log.close()
            app.memory.close()
