"""Tests for real hook firing: pre_tool interception, post_tool firing on both
success and failure, the two meanings of a declarative hook's on, and build_agent
mounting the user hooks directory with event forwarding.
"""

import json
import logging
from types import SimpleNamespace

from agent.hooks import HOOK_POINTS, HookLoader, HookRegistry
from agent.llm import FakeLLM, ToolCall
from agent.main import build_agent
from agent.policy import PolicyEngine
from agent.tools import AgentTool, Toolbelt


def _belt(hooks: HookRegistry | None) -> Toolbelt:
    def echo(text: str = "") -> str:
        return f"echo:{text}"

    def boom() -> str:
        raise ValueError("boom")

    return Toolbelt(
        {
            "echo": AgentTool(name="echo", description="echo tool", handler=echo),
            "boom": AgentTool(name="boom", description="always fails", handler=boom),
        },
        PolicyEngine(),
        hooks=hooks,
    )


class TestToolLifecycleHooks:
    async def test_pre_tool_false_intercepts(self) -> None:
        """If any pre_tool hook returns False: the handler is skipped, yet the remaining pre hooks still fire."""
        calls: list[str] = []

        async def block(**kwargs) -> bool:
            return False

        async def watch(**kwargs) -> None:
            calls.append("watch")

        hooks = HookRegistry()
        hooks.register("pre_tool", block, source="t")
        hooks.register("pre_tool", watch, source="t")
        out = await _belt(hooks).call(ToolCall("1", "echo", {"text": "hi"}))
        assert out.startswith("[已拦截]")
        assert calls == ["watch"]

    async def test_pre_tool_pass_through(self) -> None:
        async def allow(**kwargs) -> None:
            return None

        hooks = HookRegistry()
        hooks.register("pre_tool", allow, source="t")
        out = await _belt(hooks).call(ToolCall("1", "echo", {"text": "hi"}))
        assert out == "echo:hi"

    async def test_post_tool_success_and_failure(self) -> None:
        """post fires on both success and failure so hooks can observe the call outcome."""
        seen: list[dict] = []

        async def post(**kwargs) -> None:
            seen.append(kwargs)

        hooks = HookRegistry()
        hooks.register("post_tool", post, source="t")
        belt = _belt(hooks)
        await belt.call(ToolCall("1", "echo", {"text": "a"}))
        await belt.call(ToolCall("2", "boom", {}))
        assert [s["ok"] for s in seen] == [True, False]
        assert seen[0]["name"] == "echo" and seen[0]["result"] == "echo:a"
        assert seen[1]["name"] == "boom"

    def test_views_copy_hooks(self) -> None:
        """Derived views (trimmed / with_policy / with_active) keep the hook registry."""
        hooks = HookRegistry()
        belt = _belt(hooks)
        assert belt.trimmed(["echo"])._hooks is hooks
        assert belt.with_policy(PolicyEngine())._hooks is hooks
        assert belt.with_active(set())._hooks is hooks


class TestDeclarativeHooks:
    def _load(self, tmp_path, data: dict) -> HookRegistry:
        hooks = HookRegistry()
        d = tmp_path / "hooks"
        d.mkdir(exist_ok=True)
        (d / "h.json").write_text(json.dumps(data), encoding="utf-8")
        HookLoader(hooks).load_dir(d, source="user", approved=True)
        return hooks

    def test_hook_point_registers_directly(self, tmp_path) -> None:
        hooks = self._load(tmp_path, {"on": "on_user_message", "enabled": True})
        assert hooks.registered() == {"on_user_message": 1}

    async def test_event_name_wraps_on_event(self, tmp_path, caplog) -> None:
        """note.created need not be in HOOK_POINTS: it is wrapped into an on_event filter matching by event type."""
        assert (
            "note.created" not in HOOK_POINTS
        )  # event names and lifecycle points never share a namespace (contract premise)
        hooks = self._load(
            tmp_path, {"on": "note.created", "description": "note created", "enabled": True}
        )
        assert hooks.registered() == {"on_event": 1}
        with caplog.at_level(logging.INFO, logger="agent.hooks.loader"):
            await hooks.fire("on_event", event=SimpleNamespace(type="note.created"))
            await hooks.fire("on_event", event=SimpleNamespace(type="note.deleted"))
        assert sum("note created" in r.message for r in caplog.records) == 1

    def test_disabled_or_unapproved_skipped(self, tmp_path) -> None:
        hooks = HookRegistry()
        d = tmp_path / "hooks"
        d.mkdir()
        (d / "a.json").write_text(
            json.dumps({"on": "note.created", "enabled": False}), encoding="utf-8"
        )
        assert HookLoader(hooks).load_dir(d, source="user", approved=False) == 0
        assert HookLoader(hooks).load_dir(d, source="user", approved=True) == 0
        assert hooks.registered() == {}


class TestLoaderOnValidation:
    """The loader entry rejects invalid on values: no crash, no registration, no subscription entry."""

    def _load_file(self, tmp_path, data: dict) -> tuple[HookRegistry, int]:
        hooks = HookRegistry()
        d = tmp_path / "hooks"
        d.mkdir(exist_ok=True)
        (d / "h.json").write_text(json.dumps(data), encoding="utf-8")
        count = HookLoader(hooks).load_file(d / "h.json", source="user", approved=True)
        return hooks, count

    def test_star_on_rejected(self, tmp_path, caplog) -> None:
        """An on of "*" (match-all) is refused: returns 0, registers nothing, and never reaches
        event_patterns — otherwise it would hit the EventLoop sync_extra_patterns ban via subscription."""
        with caplog.at_level(logging.WARNING, logger="agent.hooks.loader"):
            hooks, count = self._load_file(tmp_path, {"on": "*", "enabled": True})
        assert count == 0
        assert hooks.registered() == {}
        assert hooks.event_patterns == ()
        assert "forbidden" in caplog.text

    def test_empty_or_missing_on_rejected(self, tmp_path, caplog) -> None:
        """An empty or missing on is refused (a filter that can never match would otherwise linger dead)."""
        with caplog.at_level(logging.WARNING, logger="agent.hooks.loader"):
            hooks, count = self._load_file(tmp_path, {"on": "", "enabled": True})
            assert count == 0
            assert hooks.registered() == {} and hooks.event_patterns == ()
            hooks2, count2 = self._load_file(tmp_path, {"enabled": True})
        assert count2 == 0
        assert hooks2.registered() == {} and hooks2.event_patterns == ()
        assert "empty" in caplog.text

    def test_non_string_on_rejected(self, tmp_path, caplog) -> None:
        """A non-string on (123 / True / null) is refused, keeping event_patterns unpolluted."""
        with caplog.at_level(logging.WARNING, logger="agent.hooks.loader"):
            for bad in (123, True, None):
                hooks, count = self._load_file(tmp_path, {"on": bad, "enabled": True})
                assert count == 0
                assert hooks.registered() == {} and hooks.event_patterns == ()
        assert "must be a string" in caplog.text

    def test_valid_wildcard_pattern_still_loads(self, tmp_path) -> None:
        """A name-qualified wildcard (note.*) is still a valid event pattern; only a bare "*" is refused."""
        hooks, count = self._load_file(tmp_path, {"on": "note.*", "enabled": True})
        assert count == 1
        assert hooks.event_patterns == ("note.*",)

    def test_bad_json_skipped_not_raised(self, tmp_path, caplog) -> None:
        """Broken JSON / non-dict files are refused individually (returns 0, registers nothing, no crash);
        startup loading (build_agent -> load_dir) skips and warns on bad files. All three loading
        paths (startup / plugins / hot reload) share the same read_hook_json fault tolerance."""
        hooks = HookRegistry()
        d = tmp_path / "hooks"
        d.mkdir()
        (d / "broken.json").write_text("{not json", encoding="utf-8")
        (d / "array.json").write_text("[]", encoding="utf-8")
        (d / "good.json").write_text(
            json.dumps({"on": "note.created", "enabled": True}), encoding="utf-8"
        )
        with caplog.at_level(logging.WARNING, logger="agent.hooks.loader"):
            count = HookLoader(hooks).load_dir(d, source="user", approved=True)
        assert count == 1  # bad file skipped, good file loaded as usual
        assert hooks.registered() == {"on_event": 1}
        assert "unparseable" in caplog.text


class TestBuildAgentWiring:
    def _build(self, tmp_path):
        return build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())

    def test_default_no_hooks_loaded(self, tmp_path) -> None:
        """Default assembly: the user hooks directory is empty and plugins/_example is not loaded;
        the loop subscribes to exactly one domain type with no "*" (exact subscription)."""
        app = self._build(tmp_path)
        try:
            assert app.hooks.registered() == {}
            # user.message drives the master; agent.step nudges the trajectory
            # projection; user.online feeds proactive outreach
            assert app.loop.patterns == ("user.message", "agent.step", "user.online")
        finally:
            app.memory.close()

    def test_user_hooks_dir_loaded(self, tmp_path) -> None:
        hooks_dir = tmp_path / "ws" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "note-watch.json").write_text(
            json.dumps({"on": "note.created", "description": "user hook", "enabled": True}),
            encoding="utf-8",
        )
        app = self._build(tmp_path)
        try:
            assert app.hooks.registered() == {"on_event": 1}
            # The declarative hook's event pattern enters the subscription; "*" still never appears
            assert "note.created" in app.loop.patterns
            assert "*" not in app.loop.patterns
        finally:
            app.memory.close()

    async def test_loop_forwards_events_to_on_event(self, tmp_path) -> None:
        """Events entering the loop reach on_event via relay (no "*" handler involved).

        This calls _dispatch directly to pin down the relay forwarding itself; arbitrary events on
        the live bus no longer reach the agent — subscriptions are decided precisely by patterns
        (see test_user_hooks_dir_loaded).
        """
        app = self._build(tmp_path)
        try:
            assert "*" not in app.loop._handlers  # "*" is banned; the relay replaces it
            seen: list[str] = []

            async def spy(event) -> None:
                seen.append(event.type)

            app.hooks.register("on_event", spy, source="test")
            await app.loop._dispatch(
                SimpleNamespace(type="note.created", trace_id=None, payload={})
            )
            assert seen == ["note.created"]
        finally:
            app.memory.close()


class TestHookAudit:
    """Every hook execution lands in the audit chain (R6: hooks are user code)."""

    async def test_fire_writes_audit_entry_with_outcome_and_duration(self) -> None:
        from agent.hooks import HookRegistry
        from platform_capability import InMemoryAuditSink

        sink = InMemoryAuditSink()
        hooks = HookRegistry(auditor=lambda entry: sink.record(entry))

        async def ok_hook(**kw):
            return "done"

        async def bad_hook(**kw):
            raise RuntimeError("boom")

        hooks.register("on_event", ok_hook, source="user:ok")
        hooks.register("on_event", bad_hook, source="user:bad")
        results = await hooks.fire("on_event", event=None)
        assert results == ["done"]  # the failure is isolated
        entries = sink.entries
        assert len(entries) == 2
        assert {e.actor_id for e in entries} == {"hook:user:ok", "hook:user:bad"}
        assert all(e.capability == "hook.on_event" for e in entries)
        bad_entry = next(e for e in entries if not e.ok)
        assert bad_entry.error_code == "HOOK_FAILED"
        assert all(e.ms >= 0 for e in entries)

    async def test_no_auditor_is_fine(self) -> None:
        from agent.hooks import HookRegistry

        async def hook(**kw):
            return 1

        hooks = HookRegistry()  # unaudited construction stays legal
        hooks.register("pre_tool", hook, source="user:h")
        assert await hooks.fire("pre_tool", name="x") == [1]
