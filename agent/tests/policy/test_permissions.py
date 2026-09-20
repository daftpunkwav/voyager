"""Tool permission modes: one mode + two lists, default full.

Covers the resolver decision table (deny in every mode, mode baselines, the
no_dangerous allow list, bash argv prefixes, unknown tools fail closed), the
central class table, the legacy shell.denied merge, and the invoke wiring
through the real assembled belt.
"""

from __future__ import annotations

from agent.build import build_agent
from agent.llm import FakeLLM, ToolCall
from agent.policy.permissions import CLASS_D, CLASS_R, TOOL_CLASS, ToolPermissions
from agent.settings import DEFS as AGENT_SETTING_DEFS
from platform_contracts import LOCAL_USER
from platform_settings import SettingsStore


class _FakeSettings:
    """Minimal settings stand: dict-backed .get, missing keys read as None."""

    def __init__(self, values: dict | None = None) -> None:
        self.values = values or {}

    def get(self, key: str):
        return self.values.get(key)


def _resolver(config, legacy_shell_denied=None) -> ToolPermissions:
    values = {"agent.permissions": config}
    if legacy_shell_denied is not None:
        values["agent.shell.denied"] = legacy_shell_denied
    return ToolPermissions(_FakeSettings(values))


class TestToolClass:
    def test_flat_classes(self) -> None:
        assert TOOL_CLASS["read"] == CLASS_R
        assert TOOL_CLASS["todowrite"] == CLASS_R
        assert TOOL_CLASS["bash"] == CLASS_D
        assert TOOL_CLASS["session.delete"] == CLASS_D
        assert TOOL_CLASS["subagent"] == CLASS_R
        assert TOOL_CLASS["agent_instance.cancel"] == CLASS_D

    def test_table_tracks_the_real_roster(self, tmp_path) -> None:
        """No stale keys: every entry names a live roster tool (the P1 flat
        names died with the aggregation; a leftover key would classify nothing
        while the real tool reads as unknown=D)."""
        from agent.build import build_agent

        app = build_agent(data_dir=tmp_path / "rd", workspace_dir=tmp_path / "ws", llm=FakeLLM())
        try:
            roster = set(app.spawner._toolbelt.names())
        finally:
            app.close()
        # activate_tools is constructed inline in graded_toolbelt (per-instance
        # view), so it never sits on the root roster
        roster.add("activate_tools")
        stale = sorted({k.split(".")[0] for k in TOOL_CLASS if k.split(".")[0] not in roster})
        assert stale == []
        # the aggregated surfaces are classified, not unknown=D
        assert tool_class_of("context", "status") == CLASS_R
        assert tool_class_of("extension", "list") == CLASS_R
        assert tool_class_of("extension", "install") == CLASS_D

    def test_unknown_is_dangerous(self) -> None:
        assert tool_class_of("notes__create_note") == CLASS_D
        assert tool_class_of("mcp__demo__search") == CLASS_D
        assert tool_class_of("no-such-tool") == CLASS_D

    def test_action_key_overrides_tool_default(self) -> None:
        # The P3 aggregation re-keys this table to "tool.action" entries with
        # the tool-level entry as default; prove the lookup order now.
        TOOL_CLASS["session"] = CLASS_R
        TOOL_CLASS["session.delete"] = CLASS_D
        try:
            assert tool_class_of("session", "list") == CLASS_R
            assert tool_class_of("session", "delete") == CLASS_D
            assert tool_class_of("session") == CLASS_R
        finally:
            TOOL_CLASS.pop("session", None)
            TOOL_CLASS.pop("session.delete", None)


def tool_class_of(name: str, action: str | None = None) -> str:
    from agent.policy.permissions import tool_class

    return tool_class(name, action)


class TestDenyList:
    def test_full_mode_default_allows_everything(self) -> None:
        rp = _resolver(None)
        assert rp.check("write", {"path": "x"}) is None
        assert rp.check("bash", {"command": "rm -rf /"}) is None
        assert rp.check("notes__create_note", {}) is None  # unknown = D, full allows

    def test_tool_level_deny(self) -> None:
        rp = _resolver({"mode": "full", "deny": ["write"], "allow": []})
        out = rp.check("write", {"path": "x"})
        assert out is not None and "权限拒绝" in out and "用户" in out
        assert rp.check("edit", {"path": "x"}) is None

    def test_action_level_deny(self) -> None:
        rp = _resolver({"mode": "full", "deny": ["todowrite.delete"], "allow": []})
        assert rp.check("todowrite", {"action": "delete"}) is not None
        assert rp.check("todowrite", {"action": "set", "items": []}) is None

    def test_bash_prefix_deny_applies_in_every_mode(self) -> None:
        for config in (
            {"mode": "full", "deny": ["bash:git push*"], "allow": []},
            {"mode": "no_dangerous", "deny": ["bash:git push*"], "allow": ["bash"]},
        ):
            rp = _resolver(config)
            assert rp.check("bash", {"command": "git push origin main"}) is not None
            assert rp.check("bash", {"command": "git push"}) is not None
            assert rp.check("bash", {"command": "git status"}) is None

    def test_bash_prefix_deny_exact_match_only(self) -> None:
        rp = _resolver({"mode": "full", "deny": ["bash:git status"], "allow": []})
        assert rp.check("bash", {"command": "git status"}) is not None
        # exact pattern: extra arguments are not covered
        assert rp.check("bash", {"command": "git status --short"}) is None

    def test_bash_prefix_deny_resists_quote_case_exe_variants(self) -> None:
        """Quoting shapes, case, and a Windows .exe suffix must not slip a
        command past its own deny prefix (the prefix list is a primary gate
        now that confirm retired)."""
        rp = _resolver({"mode": "full", "deny": ["bash:git push*"], "allow": []})
        for command in (
            '"git" push origin main',
            'git "push" origin',
            "GIT PUSH",
            "Git push",
            "git.exe push --force",
        ):
            assert rp.check("bash", {"command": command}) is not None, command
        # a differently-named command still passes
        assert rp.check("bash", {"command": "git fetch origin"}) is None


class TestModes:
    def test_read_only_hard_ceiling(self) -> None:
        rp = _resolver({"mode": "read_only", "deny": [], "allow": ["bash"]})
        assert rp.check("read", {"path": "x"}) is None
        assert rp.check("grep", {"pattern": "x"}) is None
        # the allow list is not consulted in read_only
        assert rp.check("bash", {"command": "ls"}) is not None
        assert rp.check("write", {"path": "x"}) is not None
        # unknown tools (domain bridges, mcp) fail closed
        assert rp.check("notes__create_note", {}) is not None

    def test_no_dangerous_rejects_d_and_unknown(self) -> None:
        rp = _resolver({"mode": "no_dangerous", "deny": [], "allow": []})
        assert rp.check("read", {"path": "x"}) is None
        assert rp.check("web_fetch", {"url": "https://x"}) is None
        assert rp.check("write", {"path": "x"}) is not None
        assert rp.check("extension", {"kind": "plugin", "action": "install"}) is not None
        assert rp.check("mcp__demo__search", {"query": "x"}) is not None

    def test_no_dangerous_allows_aggregated_read_tools(self) -> None:
        """The aggregated context/extension surfaces must not fall through to
        unknown=D: their P1 flat names (context_status, list_plugins, ...) are
        gone, so the tool-level keys are what read_only/no_dangerous consult."""
        rp = _resolver({"mode": "no_dangerous", "deny": [], "allow": []})
        assert rp.check("context", {"action": "status"}) is None
        assert rp.check("extension", {"kind": "plugin", "action": "list"}) is None
        assert rp.check("extension", {"kind": "mcp", "action": "preview"}) is None
        # lifecycle actions stay D even though the tool default is R
        assert rp.check("extension", {"kind": "hook", "action": "reload"}) is not None
        assert rp.check("extension", {"kind": "plugin", "action": "uninstall"}) is not None

    def test_no_dangerous_allow_rescues_whole_tool(self) -> None:
        rp = _resolver({"mode": "no_dangerous", "deny": [], "allow": ["bash"]})
        assert rp.check("bash", {"command": "anything"}) is None
        assert rp.check("write", {"path": "x"}) is not None

    def test_no_dangerous_bash_prefix_allow(self) -> None:
        rp = _resolver({"mode": "no_dangerous", "deny": [], "allow": ["bash:npm *"]})
        assert rp.check("bash", {"command": "npm test"}) is None
        assert rp.check("bash", {"command": "rm -rf /"}) is not None

    def test_deny_wins_over_allow(self) -> None:
        rp = _resolver(
            {
                "mode": "no_dangerous",
                "deny": ["bash:git push*"],
                "allow": ["bash:git *"],
            }
        )
        assert rp.check("bash", {"command": "git push origin"}) is not None
        assert rp.check("bash", {"command": "git status"}) is None


class TestDegradeAndLegacy:
    def test_malformed_config_falls_back_to_full(self) -> None:
        rp = ToolPermissions(_FakeSettings({"agent.permissions": "not-a-dict"}))
        assert rp.check("write", {"path": "x"}) is None
        rp = _resolver({"mode": "bogus", "deny": "nope", "allow": 3})
        assert rp.check("write", {"path": "x"}) is None

    def test_missing_setting_reads_as_full(self) -> None:
        rp = ToolPermissions(_FakeSettings({}))
        assert rp.check("bash", {"command": "x"}) is None

    def test_legacy_shell_denied_merges_as_bash_prefixes(self) -> None:
        rp = _resolver(None, legacy_shell_denied=["git push *", "rm *"])
        assert rp.check("bash", {"command": "git push origin main"}) is not None
        assert rp.check("bash", {"command": "rm -rf build"}) is not None
        assert rp.check("bash", {"command": "ls"}) is None

    def test_store_failure_reads_as_full(self) -> None:
        class _Broken:
            def get(self, key: str):
                raise RuntimeError("store offline")

        rp = ToolPermissions(_Broken())
        assert rp.check("write", {"path": "x"}) is None


class TestInvokeWiring:
    """The resolver sits in front of the real belt: mode/deny rejections reach
    the model as text, and the default full mode keeps the retired-confirm
    behavior (calls execute, no [需确认] fallback)."""

    async def _app(self, tmp_path, config=None):
        settings = SettingsStore(tmp_path / "settings.db")
        settings.register_fresh(AGENT_SETTING_DEFS)
        if config is not None:
            await settings.set("agent.permissions", config, LOCAL_USER)
        return build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            settings_store=settings,
        )

    async def test_read_only_mode_blocks_write_through_real_belt(self, tmp_path) -> None:
        app = await self._app(tmp_path, {"mode": "read_only", "deny": [], "allow": []})
        try:
            belt = app.spawner._toolbelt
            out = await belt.call(ToolCall("1", "read", {"path": "ok.txt"}))
            assert "权限拒绝" not in out
            out = await belt.call(ToolCall("2", "write", {"path": "no.txt", "content": "x"}))
            assert out.startswith("[权限拒绝]")
            out = await belt.call(ToolCall("3", "bash", {"command": "echo hi"}))
            assert out.startswith("[权限拒绝]")
        finally:
            app.close()

    async def test_tool_deny_rejects_and_default_full_executes(self, tmp_path) -> None:
        app = await self._app(tmp_path, {"mode": "full", "deny": ["memory.clear"], "allow": []})
        try:
            belt = app.spawner._toolbelt
            out = await belt.call(ToolCall("1", "memory", {"action": "clear", "zone": "working"}))
            assert out.startswith("[权限拒绝]")
            # full mode: an irreversible app-dimension call executes directly
            # (confirm retired; the resolver + app lists are the gates)
            out = await belt.call(ToolCall("2", "read", {"path": "ok.txt"}))
            assert "[需确认]" not in out and "[权限拒绝]" not in out
        finally:
            app.close()
