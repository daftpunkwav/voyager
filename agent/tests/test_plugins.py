"""Tests for plugin discovery, bundle approval, item approval, and loading.

All fixtures use tmp plugin directories injected via build_agent's plugins_dir, with no
reliance on the repo's plugins/_example contents; the not-loaded-by-default baseline is
pinned by test_skills/test_hooks. After approve/revoke, hooks.event_patterns are pushed
live to the EventLoop (loop.sync_extra_patterns); loop.patterns is no longer frozen to
the boot-time snapshot.
"""

import asyncio
import json
import os
import shutil
import zipfile
from pathlib import Path

import pytest
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


def make_plugin(
    root: Path,
    name: str = "example",
    *,
    version: str = "0.1.0",
    description: str = "Test plugin",
    skills: tuple[str, ...] = ("skills/daily-note",),
    hooks: tuple[str, ...] = ("hooks/on-note-created.json",),
    mcp: str | None = "mcp.json",
    hook_enabled: bool = False,
    hook_specs: dict[str, dict] | None = None,  # {rel: {"on","enabled","description"}}
    mcp_servers: dict[str, dict]
    | None = None,  # overrides mcp.json servers (for multi-server cases)
    raw_manifest: dict | None = None,
) -> Path:
    """Builds a declarative plugin directory; fields are optional, mcp=None means no MCP config."""
    d = root / name
    d.mkdir(parents=True)
    manifest = (
        raw_manifest
        if raw_manifest is not None
        else {
            "name": name,
            "version": version,
            "description": description,
            "permissions": {"scopes": ["notes.write"], "network": "off", "fs": "none"},
            "contains": {
                "skills": list(skills),
                "hooks": list(hooks),
                "mcp": mcp,
            },
        }
    )
    (d / "plugin.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    for skill in skills:
        skill_dir = d / skill
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            f"# {skill_dir.name}\n\nTest skill full text.\n", encoding="utf-8"
        )
    spec_default = hook_specs or {}
    for hook in hooks:
        hook_path = d / hook
        hook_path.parent.mkdir(parents=True, exist_ok=True)
        spec = spec_default.get(hook, {})
        hook_path.write_text(
            json.dumps(
                {
                    "on": spec.get("on", "note.created"),
                    "description": spec.get("description", f"{hook} hook"),
                    "enabled": spec.get("enabled", hook_enabled),
                }
            ),
            encoding="utf-8",
        )
    if mcp:
        servers = (
            mcp_servers
            if mcp_servers is not None
            else {
                f"{name}-search": {"command": "npx", "args": ["-y", "x"]},
            }
        )
        (d / mcp).write_text(json.dumps({"servers": servers}), encoding="utf-8")
    return d


def build(tmp_path, **overrides):
    """build_agent with the plugin root fixed to tmp_path/plugins; everything else overridable."""
    plugins_root = tmp_path / "plugins"
    plugins_root.mkdir(exist_ok=True)
    app = build_agent(
        data_dir=tmp_path / "rd",
        workspace_dir=tmp_path / "ws",
        llm=FakeLLM(),
        plugins_dir=plugins_root,
        **overrides,
    )
    return app


@pytest.fixture()
def app(tmp_path):
    a = build(tmp_path)
    yield a
    a.memory.close()


async def _approve(app, name: str = "example") -> dict:
    return await execute(
        app.registry, "set_plugin_approval", USER_CTX, {"name": name, "approved": True}
    )


async def _approve_item(app, name: str = "example", **items) -> dict:
    """Item-approval helper: items are the skills/hooks/mcp parameters (lists or '*'/None)."""
    return await execute(
        app.registry,
        "set_plugin_approval",
        USER_CTX,
        {"name": name, "approved": True, "granularity": "item", **items},
    )


class TestDiscover:
    """Discovery: broken manifests are skipped; `_`-prefixed directories are listed but not loaded."""

    def test_underscore_prefix_listed(self, tmp_path) -> None:
        """`_`-prefixed directories still show up in list (visible when listed, loaded only when approved)."""
        make_plugin(tmp_path / "plugins", "_example")
        app = build(tmp_path)
        try:
            names = [m.name for m in app.plugins.manifests()]
            assert "_example" in names
            assert [i["name"] for i in app.plugins.list()] == ["_example"]
        finally:
            app.memory.close()

    def test_bad_or_missing_manifest_skipped(self, tmp_path) -> None:
        """Directories with broken JSON / missing name / no plugin.json are skipped without breaking boot."""
        root = tmp_path / "plugins"
        root.mkdir()
        (root / "broken").mkdir()
        (root / "broken" / "plugin.json").write_text("{not-json", encoding="utf-8")
        (root / "no-name").mkdir()
        (root / "no-name" / "plugin.json").write_text('{"version": "1.0"}', encoding="utf-8")
        (root / "not-json").mkdir()
        (root / "plain").mkdir()  # no manifest at all
        app = build(tmp_path)
        try:
            assert app.plugins.manifests() == []
        finally:
            app.memory.close()

    def test_missing_optional_keys_defaulted(self, tmp_path) -> None:
        """A manifest with only name is valid: version/description/permissions/contains get defaults."""
        make_plugin(tmp_path / "plugins", "minimal", raw_manifest={"name": "minimal"})
        app = build(tmp_path)
        try:
            (item,) = app.plugins.list()
            assert item["name"] == "minimal"
            assert item["version"] == "" and item["description"] == ""
            assert item["permissions"] == {"scopes": [], "network": "", "fs": ""}
            assert item["contains"] == {"skills": 0, "hooks": 0, "mcp": False}
        finally:
            app.memory.close()

    def test_list_shape_stable(self, app, tmp_path) -> None:
        """list_plugins contract shape (normalized permissions + contains counts + path + item details)."""
        make_plugin(tmp_path / "plugins", "example")
        assert app.plugins.list() == [
            {
                "name": "example",
                "version": "0.1.0",
                "description": "Test plugin",
                "approved": False,
                "granularity": "",
                "permissions": {"scopes": ["notes.write"], "network": "off", "fs": "none"},
                "contains": {"skills": 1, "hooks": 1, "mcp": True},
                "skills": [{"name": "daily-note", "approved": False}],
                "hooks": [
                    {
                        "path": "hooks/on-note-created.json",
                        "on": "note.created",
                        "enabled": False,
                        "approved": False,
                    }
                ],
                "mcp": [
                    {
                        "id": "example-search",
                        "approved": False,
                        "registered": False,
                        "tools_approved": [],
                    }
                ],
                "path": "example",
            }
        ]

    async def test_capability_list_plugins_shape(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        out = await execute(app.registry, "list_plugins", USER_CTX, {})
        assert out == {"items": app.plugins.list()}
        assert out["items"][0]["name"] == "example"


class TestPathJail:
    """contains relative paths must not escape the plugin directory."""

    def test_escape_and_absolute_rejected(self, app, tmp_path) -> None:
        """contains entries using ../ or absolute paths: counted as 0 and never listed."""
        root = tmp_path / "plugins"
        make_plugin(root, "escapee", skills=("../outside/skill-a",))
        # The escape target genuinely exists outside the plugin directory
        outside = tmp_path / "outside" / "skill-a"
        outside.mkdir(parents=True)
        (outside / "SKILL.md").write_text("# outside\n", encoding="utf-8")
        make_plugin(root, "abs", skills=(str(tmp_path / "evil" / "skill-b"),), mcp=None, hooks=())
        items = {i["name"]: i for i in app.plugins.list()}
        assert items["escapee"]["contains"]["skills"] == 0
        assert items["abs"]["contains"]["skills"] == 0

    async def test_escape_not_loaded_after_approve(self, tmp_path) -> None:
        root = tmp_path / "plugins"
        make_plugin(root, "escapee", skills=("../outside/skill-a",))
        outside = tmp_path / "outside" / "skill-a"
        outside.mkdir(parents=True)
        (outside / "SKILL.md").write_text("# outside\n", encoding="utf-8")
        app = build(tmp_path)
        try:
            out = await _approve(app, "escapee")
            assert out["loaded"]["skills"] == []  # escaping entries are not loaded
            assert "skill-a" not in [e["name"] for e in app.skills.index()]
        finally:
            app.memory.close()


class TestApproval:
    """Approval capability surface: USER-only, granularity handling."""

    async def test_approve_returns_contract_shape(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        out = await _approve(app)
        assert out == {
            "name": "example",
            "approved": True,
            "loaded": {
                "skills": ["daily-note"],
                "hooks": 0,
                "mcp_registered": 1,
                "mcp_skipped": False,
            },
            "skipped": {"skills": [], "hooks": [], "mcp": []},
        }

    async def test_agent_actor_rejected(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry,
                "set_plugin_approval",
                AGENT_CTX,
                {"name": "example", "approved": True},
            )
        assert exc.value.body.code == "AGENT.FORBIDDEN"
        assert app.settings.get("agent.plugins.approved") == []

    async def test_no_actor_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry, "set_plugin_approval", None, {"name": "example", "approved": True}
            )
        assert exc.value.body.code == "CAPABILITY.AUTH_REQUIRED"

    async def test_granularity_unknown_rejected(self, app, tmp_path) -> None:
        """Invalid granularity values still yield INVALID_INPUT (only bundle/item are accepted)."""
        make_plugin(tmp_path / "plugins", "example")
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry,
                "set_plugin_approval",
                USER_CTX,
                {"name": "example", "approved": True, "granularity": "everything"},
            )
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    async def test_unknown_plugin_not_found(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await _approve(app, "ghost")
        assert exc.value.body.code == "AGENT.NOT_FOUND"


class TestPersistAndReload:
    """Approval-list persistence, loading on restart, and hot-unload on revoke."""

    async def test_approved_survives_rebuild(self, tmp_path) -> None:
        root = tmp_path / "plugins"
        make_plugin(root, "example", hook_enabled=True)
        app1 = build(tmp_path)
        try:
            await _approve(app1)
            assert app1.settings.get("agent.plugins.approved") == ["example"]
            assert "daily-note" in [e["name"] for e in app1.skills.index()]
            assert app1.hooks.registered() == {"on_event": 1}
        finally:
            app1.close()
        app2 = build(tmp_path)  # restart: same data_dir, reads the persisted list
        try:
            assert "daily-note" in [e["name"] for e in app2.skills.index()]
            assert app2.hooks.registered() == {"on_event": 1}
            assert "note.created" in app2.loop.patterns
        finally:
            app2.close()

    async def test_unapproved_default_not_loaded(self, app, tmp_path) -> None:
        """Unapproved (default): no skill in the index, no hook loaded, no MCP registered (the C3 baseline)."""
        make_plugin(tmp_path / "plugins", "example", hook_enabled=True)
        assert "daily-note" not in [e["name"] for e in app.skills.index()]
        assert app.hooks.registered() == {}
        assert await execute(app.registry, "list_mcp_servers", USER_CTX, {}) == []

    async def test_unapprove_hot_unloads(self, tmp_path) -> None:
        root = tmp_path / "plugins"
        make_plugin(root, "example", hook_enabled=True)
        app = build(tmp_path)
        try:
            await _approve(app)
            assert "daily-note" in [e["name"] for e in app.skills.index()]
            out = await execute(
                app.registry,
                "set_plugin_approval",
                USER_CTX,
                {"name": "example", "approved": False},
            )
            assert out["approved"] is False
            assert out["unloaded"] == {"skills": 1, "hooks": 1}
            # Hot unload: gone from list immediately, hook registrations and event subscriptions withdrawn together
            assert "daily-note" not in [e["name"] for e in app.skills.index()]
            assert app.hooks.registered() == {}
            assert "note.created" not in app.loop.patterns
            assert app.settings.get("agent.plugins.approved") == []
            assert out["loaded"] == {
                "skills": [],
                "hooks": 0,
                "mcp_registered": 0,
                "mcp_skipped": False,
            }
        finally:
            app.memory.close()

    async def test_unapprove_survives_rebuild(self, tmp_path) -> None:
        root = tmp_path / "plugins"
        make_plugin(root, "example", hook_enabled=True)
        app1 = build(tmp_path)
        try:
            await _approve(app1)
        finally:
            app1.close()
        app2 = build(tmp_path)
        try:
            await execute(
                app2.registry,
                "set_plugin_approval",
                USER_CTX,
                {"name": "example", "approved": False},
            )
        finally:
            app2.close()
        app3 = build(tmp_path)
        try:
            assert "daily-note" not in [e["name"] for e in app3.skills.index()]
            assert app3.settings.get("agent.plugins.approved") == []
        finally:
            app3.close()

    async def test_unapprove_purges_stale_entry(self, tmp_path) -> None:
        """Revoking a stale dead list entry (plugin directory already deleted) clears the list without raising NOT_FOUND."""
        root = tmp_path / "plugins"
        make_plugin(root, "example", hook_enabled=True)
        app = build(tmp_path)
        try:
            await _approve(app)
            assert app.settings.get("agent.plugins.approved") == ["example"]
            shutil.rmtree(root / "example")
            out = await execute(
                app.registry,
                "set_plugin_approval",
                USER_CTX,
                {"name": "example", "approved": False},
            )
            assert out["approved"] is False
            assert out["unloaded"] == {"skills": 0, "hooks": 0}  # manifest gone: hot unload skipped
            assert app.settings.get("agent.plugins.approved") == []
        finally:
            app.close()

    async def test_unload_keeps_pattern_declared_by_other(self, tmp_path) -> None:
        """Two plugins declaring the same event pattern: revoking one keeps the other's hook registration and declaration."""
        root = tmp_path / "plugins"
        make_plugin(root, "alpha", hook_enabled=True)
        make_plugin(root, "beta", hook_enabled=True)
        app = build(tmp_path)
        try:
            await _approve(app, "alpha")
            await _approve(app, "beta")
            assert app.hooks.registered() == {"on_event": 2}
            await execute(
                app.registry, "set_plugin_approval", USER_CTX, {"name": "alpha", "approved": False}
            )
            assert app.hooks.registered() == {"on_event": 1}  # beta's hook remains
            assert app.hooks.event_patterns == (
                "note.created",
            )  # beta's declaration was not mistakenly withdrawn
        finally:
            app.close()


class TestSkillHookLoad:
    """After approval the skill enters the index with readable full text, hooks enter the registry; unapproved ones do not load."""

    async def test_load_skill_full_text(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        await _approve(app)
        doc = await execute(app.registry, "load_skill", USER_CTX, {"name": "daily-note"})
        assert doc["name"] == "daily-note" and "Test skill full text" in doc["text"]

    async def test_enabled_hook_loaded_disabled_not(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example", hook_enabled=False)
        out = await _approve(app)
        assert out["loaded"]["hooks"] == 0  # an enabled=false hook counts as 0 loaded
        assert app.hooks.registered() == {}

    async def test_repeated_approve_idempotent(self, app, tmp_path) -> None:
        """Repeated approval (retry / re-approve after startup): skill roots dedupe, hooks register once, subscriptions never double.

        Runtime subscription sync: approval pushes straight to the loop, so loop.patterns is
        asserted directly here.
        """
        make_plugin(tmp_path / "plugins", "example", hook_enabled=True)
        await _approve(app)
        await _approve(app)
        names = [e["name"] for e in app.skills.index()]
        assert names.count("daily-note") == 1
        assert app.hooks.registered() == {"on_event": 1}
        assert app.hooks.event_patterns.count("note.created") == 1
        assert app.loop.patterns.count("note.created") == 1  # the runtime snapshot does not double


class TestMcpRegistration:
    """Thin MCP integration: entries are registered pending approval; tools are never auto-approved."""

    async def test_servers_registered_pending_approval(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        await _approve(app)
        servers = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
        assert [s["id"] for s in servers] == ["example-search"]
        assert servers[0]["approved"] == []  # registered only, no tools approved
        tools = {
            t["name"] for t in await execute(app.registry, "tools", USER_CTX, {"action": "list"})
        }
        assert not [n for n in tools if n.startswith("mcp__")]

    async def test_missing_mcp_json_skipped(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example", mcp=None)
        out = await _approve(app)
        assert out["loaded"]["mcp_registered"] == 0
        assert out["loaded"]["mcp_skipped"] is True

    async def test_bad_or_empty_mcp_json_skipped(self, app, tmp_path) -> None:
        root = tmp_path / "plugins"
        d = make_plugin(root, "example")
        (d / "mcp.json").write_text("{bad", encoding="utf-8")
        out = await _approve(app)
        assert out["loaded"]["mcp_skipped"] is True
        # Re-approve after switching to empty servers: the mcp step is still treated as skipped
        (d / "mcp.json").write_text('{"servers": {}}', encoding="utf-8")
        out2 = await _approve(app)
        assert out2["loaded"]["mcp_registered"] == 0
        assert out2["loaded"]["mcp_skipped"] is True

    async def test_invalid_server_entry_skipped_without_fail(self, app, tmp_path) -> None:
        """A broken server entry (missing command) is skipped; skill/hook approval still succeeds."""
        root = tmp_path / "plugins"
        d = make_plugin(root, "example")
        (d / "mcp.json").write_text(
            json.dumps({"servers": {"bad-srv": {"command": ""}}}), encoding="utf-8"
        )
        out = await _approve(app)
        assert out["loaded"]["mcp_registered"] == 0
        assert out["loaded"]["mcp_skipped"] is False  # the file parses; only the entry was skipped
        assert out["loaded"]["skills"] == ["daily-note"]

    async def test_existing_server_id_not_overwritten(self, app, tmp_path) -> None:
        """A same-id entry added manually by the user: skipped without overwrite, its approval state intact."""
        make_plugin(tmp_path / "plugins", "example")
        await execute(
            app.registry,
            "add_mcp_server",
            USER_CTX,
            {"id": "example-search", "kind": "stdio", "command": "npx"},
        )
        await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "example-search", "names": ["*"]}
        )
        out = await _approve(app)
        assert out["loaded"]["mcp_registered"] == 0
        servers = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
        assert servers[0]["approved"] == [
            "*"
        ]  # the original package approval untouched by plugin approval


# ---- Item approval (per-item) ----


def make_two_of_each(root: Path, name: str = "multi") -> Path:
    """Item fixture: 2 skills + 2 hooks (different on values) + 2 MCP servers; hooks enabled by default."""
    return make_plugin(
        root,
        name,
        skills=("skills/alpha", "skills/beta"),
        hooks=("hooks/h-note.json", "hooks/h-todo.json"),
        mcp_servers={
            f"{name}-s1": {"command": "npx", "args": ["-y", "s1"]},
            f"{name}-s2": {"command": "npx", "args": ["-y", "s2"]},
        },
        hook_specs={
            "hooks/h-note.json": {"on": "note.created", "enabled": True},
            "hooks/h-todo.json": {"on": "todo.created", "enabled": True},
        },
    )


def loaded_skill_names(app) -> set[str]:
    """Skill names in the app.skills index belonging to the item fixture (alpha/beta)."""
    return {e["name"] for e in app.skills.index()} & {"alpha", "beta"}


class TestItemApproval:
    """Item approval loads only the checked subset; MCP only registers the listed servers, never auto-approving tools."""

    async def test_item_skills_subset_only(self, app, tmp_path) -> None:
        make_two_of_each(tmp_path / "plugins")
        out = await _approve_item(app, "multi", skills=["alpha"])
        assert out["granularity"] == "item"
        assert out["loaded"]["skills"] == ["alpha"]
        assert out["loaded"]["hooks"] == 0
        assert loaded_skill_names(app) == {"alpha"}
        # Unchecked skills are unreadable (absent from list_skills, load_skill gives NOT_FOUND)
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "load_skill", USER_CTX, {"name": "beta"})
        assert exc.value.body.code == "AGENT.NOT_FOUND"
        assert app.settings.get("agent.plugins.approvals") == {
            "multi": {"skills": ["alpha"], "hooks": [], "mcp": []}
        }
        assert app.settings.get("agent.plugins.approved") == []  # never enters the bundle list

    async def test_item_hook_subset_only(self, app, tmp_path) -> None:
        make_two_of_each(tmp_path / "plugins")
        out = await _approve_item(app, "multi", hooks=["hooks/h-note.json"])
        assert out["loaded"]["hooks"] == 1
        # Only h-note approved: h-note's on enters registry/subscription; h-todo (enabled) stays unapproved and never fires
        assert app.hooks.registered() == {"on_event": 1}
        assert app.hooks.event_patterns == ("note.created",)

    async def test_item_mcp_selected_only_registered(self, app, tmp_path) -> None:
        make_two_of_each(tmp_path / "plugins")
        out = await _approve_item(app, "multi", mcp=["multi-s1"])
        assert out["loaded"]["mcp_registered"] == 1
        servers = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
        assert [s["id"] for s in servers] == ["multi-s1"]
        assert (
            servers[0]["approved"] == []
        )  # registered pending approval; tools never auto-approved
        tools = {
            t["name"] for t in await execute(app.registry, "tools", USER_CTX, {"action": "list"})
        }
        assert not [n for n in tools if n.startswith("mcp__")]

    async def test_item_mcp_empty_not_registered(self, app, tmp_path) -> None:
        make_two_of_each(tmp_path / "plugins")
        await _approve_item(app, "multi", skills=["alpha"], mcp=[])
        assert await execute(app.registry, "list_mcp_servers", USER_CTX, {}) == []
        assert app.settings.get("agent.plugins.approvals")["multi"]["mcp"] == []

    async def test_item_mcp_star_registers_all(self, app, tmp_path) -> None:
        make_two_of_each(tmp_path / "plugins")
        out = await _approve_item(app, "multi", mcp="*")
        assert out["loaded"]["mcp_registered"] == 2
        servers = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
        assert {s["id"] for s in servers} == {"multi-s1", "multi-s2"}


class TestItemValidation:
    """Empty submissions and unknown item shapes are rejected; unknown names are skipped and disclosed in skipped."""

    async def test_empty_item_rejected(self, app, tmp_path) -> None:
        """An empty submission (all three categories empty) -> INVALID_INPUT, never recording an approval that loaded nothing."""
        make_plugin(tmp_path / "plugins", "example")
        with pytest.raises(ServiceError) as exc:
            await _approve_item(app, skills=[], hooks=[], mcp=[])
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert app.settings.get("agent.plugins.approvals") == {}
        assert "daily-note" not in [e["name"] for e in app.skills.index()]

    async def test_unknown_items_skipped_and_disclosed(self, app, tmp_path) -> None:
        """Skill/hook/MCP names absent from the manifest: skipped, reported in skipped; wrong names are never silently loaded."""
        make_two_of_each(tmp_path / "plugins")
        out = await _approve_item(
            app,
            "multi",
            skills=["alpha", "ghost-skill"],
            hooks=["hooks/h-note.json", "hooks/ghost.json"],
            mcp=["multi-s1", "ghost-srv"],
        )
        assert out["loaded"]["skills"] == ["alpha"]
        assert out["loaded"]["hooks"] == 1
        assert out["loaded"]["mcp_registered"] == 1
        assert out["skipped"] == {
            "skills": ["ghost-skill"],
            "hooks": ["hooks/ghost.json"],
            "mcp": ["ghost-srv"],
        }
        # Persistence keeps the checked names (user intent is never rewritten; reinstalling once the file returns just works)
        assert app.settings.get("agent.plugins.approvals")["multi"]["skills"] == [
            "alpha",
            "ghost-skill",
        ]

    async def test_malformed_item_args_rejected(self, app, tmp_path) -> None:
        """skills of a non-'*' / non-list type -> INVALID_INPUT (dirty types are not treated as empty selections)."""
        make_two_of_each(tmp_path / "plugins")
        for bad in (123, [""], ["  "], {"alpha": 1}):
            with pytest.raises(ServiceError) as exc:
                await _approve_item(app, "multi", skills=bad)
            assert exc.value.body.code == "AGENT.INVALID_INPUT"


class TestItemPersistence:
    """Item persistence, legacy bundle-key migration on the read side, loading across restarts, idempotency, and write-side exclusivity."""

    async def test_item_survives_rebuild(self, tmp_path) -> None:
        root = tmp_path / "plugins"
        make_two_of_each(root)
        app1 = build(tmp_path)
        try:
            await _approve_item(app1, "multi", skills=["alpha"], hooks=["hooks/h-note.json"])
        finally:
            app1.close()
        app2 = build(tmp_path)
        try:
            assert loaded_skill_names(app2) == {"alpha"}
            assert app2.hooks.registered() == {"on_event": 1}
            assert app2.hooks.event_patterns == ("note.created",)
        finally:
            app2.close()

    async def test_legacy_approved_migrates_as_star(self, tmp_path) -> None:
        """Only the legacy approved key has a name and no new key -> the read side treats it as a bundle (all skills/hooks load)."""
        root = tmp_path / "plugins"
        make_two_of_each(root)
        app1 = build(tmp_path)
        try:
            await _approve(app1, "multi")  # bundle: writes approved, leaves approvals untouched
        finally:
            app1.close()
        app2 = build(tmp_path)
        try:
            assert app2.settings.get("agent.plugins.approved") == ["multi"]
            assert app2.settings.get("agent.plugins.approvals") == {}
            assert loaded_skill_names(app2) == {"alpha", "beta"}
            assert app2.hooks.registered() == {"on_event": 2}
        finally:
            app2.close()

    async def test_persisted_empty_approval_treated_as_unapproved(self, app, tmp_path) -> None:
        """Read and write sides agree: a persisted empty item selection (hand-written / legacy bad data) counts as unapproved — nothing loads, nothing misleads."""
        make_two_of_each(tmp_path / "plugins")
        # Write directly, bypassing the capability layer (a user_only key reachable via the settings API): all three lists empty
        await execute(
            app.registry,
            "set_setting",
            USER_CTX,
            {
                "key": "agent.plugins.approvals",
                "value": {"multi": {"skills": [], "hooks": [], "mcp": []}},
            },
        )
        item = next(i for i in app.plugins.list() if i["name"] == "multi")
        assert item["approved"] is False
        assert item["granularity"] == ""
        assert loaded_skill_names(app) == set()  # nothing loaded
        # A bundle approval can overwrite the leftover empty key (self-healing path)
        await _approve(app, "multi")
        assert app.settings.get("agent.plugins.approvals") == {}
        assert loaded_skill_names(app) == {"alpha", "beta"}

    async def test_item_then_bundle_overrides(self, app, tmp_path) -> None:
        """Write-side exclusivity: item then bundle -> moves to approved and clears approvals (unambiguous on the read side)."""
        make_two_of_each(tmp_path / "plugins")
        await _approve_item(app, "multi", skills=["alpha"])
        await _approve(app, "multi")
        assert app.settings.get("agent.plugins.approved") == ["multi"]
        assert app.settings.get("agent.plugins.approvals") == {}
        assert loaded_skill_names(app) == {"alpha", "beta"}
        item = next(i for i in app.plugins.list() if i["name"] == "multi")
        assert item["granularity"] == "bundle"
        assert all(s["approved"] for s in item["skills"])

    async def test_bundle_then_item_overrides(self, app, tmp_path) -> None:
        """Write-side exclusivity: bundle then item -> moves to approvals and clears approved."""
        make_two_of_each(tmp_path / "plugins")
        await _approve(app, "multi")
        await _approve_item(app, "multi", skills=["beta"])
        assert app.settings.get("agent.plugins.approved") == []
        assert app.settings.get("agent.plugins.approvals") == {
            "multi": {"skills": ["beta"], "hooks": [], "mcp": []}
        }
        # alpha loaded under the bundle has been hot-unloaded; only beta remains
        assert loaded_skill_names(app) == {"beta"}

    async def test_item_reapply_idempotent(self, app, tmp_path) -> None:
        """Repeated set(item) is idempotent (unload first, then apply): skill roots, hooks, and subscriptions never double."""
        make_two_of_each(tmp_path / "plugins")
        await _approve_item(app, "multi", hooks=["hooks/h-note.json"])
        await _approve_item(app, "multi", hooks=["hooks/h-note.json"])
        assert app.hooks.registered() == {"on_event": 1}
        assert app.hooks.event_patterns == ("note.created",)
        assert app.settings.get("agent.plugins.approvals")["multi"]["hooks"] == [
            "hooks/h-note.json"
        ]

    async def test_unapprove_clears_both_keys(self, app, tmp_path) -> None:
        """Revoking clears both the bundle and item keys and hot-unloads."""
        make_two_of_each(tmp_path / "plugins")
        await _approve_item(app, "multi", skills=["alpha"], hooks=["hooks/h-note.json"])
        out = await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "multi", "approved": False}
        )
        assert out["approved"] is False
        assert out["unloaded"] == {"skills": 1, "hooks": 1}
        assert app.settings.get("agent.plugins.approved") == []
        assert app.settings.get("agent.plugins.approvals") == {}
        assert loaded_skill_names(app) == set()
        assert app.hooks.registered() == {}


class TestItemPathJailAndManifest:
    """The path jail still applies to item paths; stale entries whose directories were deleted are skipped without crashing; manifest details."""

    async def test_item_hook_jail_applies(self, app, tmp_path) -> None:
        """An item-checked escaping hook -> resolve_within refuses it, no file loads, and skipped discloses it instead of loading the wrong name."""
        root = tmp_path / "plugins"
        make_plugin(root, "escapee", hooks=("../outside/x.json",), mcp=None)
        outside = tmp_path / "outside"
        outside.mkdir(exist_ok=True)
        (outside / "x.json").write_text(
            json.dumps({"on": "note.created", "enabled": True}), encoding="utf-8"
        )
        out = await _approve_item(app, "escapee", hooks=["../outside/x.json"])
        assert out["loaded"]["hooks"] == 0
        assert out["skipped"] == {"skills": [], "hooks": ["../outside/x.json"], "mcp": []}
        assert app.hooks.registered() == {}

    async def test_stale_item_entry_directory_removed_no_boot_crash(self, tmp_path) -> None:
        """Directory deleted but approvals linger -> startup skips without crashing."""
        root = tmp_path / "plugins"
        make_two_of_each(root)
        app1 = build(tmp_path)
        try:
            await _approve_item(app1, "multi", skills=["alpha"])
        finally:
            app1.close()
        shutil.rmtree(root / "multi")
        app2 = build(tmp_path)
        try:
            assert loaded_skill_names(app2) == set()  # no crash, nothing loaded
        finally:
            app2.close()

    async def test_plugin_mcp_tools_approved_read_only(self, app, tmp_path) -> None:
        """The manifest MCP row: tools_approved reads the existing MCP storage (visible after registration and a package approval)."""
        make_plugin(tmp_path / "plugins", "example")
        before = app.plugins.list()[0]
        assert before["mcp"] == [
            {"id": "example-search", "approved": False, "registered": False, "tools_approved": []}
        ]
        # The user manually approves this MCP's tools (external MCP block)
        await execute(
            app.registry,
            "add_mcp_server",
            USER_CTX,
            {"id": "example-search", "kind": "stdio", "command": "npx"},
        )
        await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "example-search", "names": ["*"]}
        )
        after = app.plugins.list()[0]
        assert after["mcp"][0]["registered"] is True
        assert after["mcp"][0]["tools_approved"] == ["*"]
        assert after["mcp"][0]["approved"] is False  # the plugin's own item approval is still false

    async def test_legacy_approved_list_shows_bundle_granularity(self, app, tmp_path) -> None:
        """A bundle approval (old or new data alike) shows granularity='bundle' in the manifest with every detail approved."""
        make_two_of_each(tmp_path / "plugins")
        await _approve(app, "multi")
        item = next(i for i in app.plugins.list() if i["name"] == "multi")
        assert item["approved"] is True
        assert item["granularity"] == "bundle"
        assert all(s["approved"] for s in item["skills"])
        assert all(h["approved"] for h in item["hooks"])
        assert all(m["approved"] for m in item["mcp"])


class TestItemPatternRetention:
    """_pattern_still_wanted judges by whether an item approval actually loaded.

    Trusting the manifest declaration alone would let an item plugin that never checked the
    hook keep a revoked plugin's pattern alive, leaving event_patterns dangling at runtime
    (registration withdrawn, subscription declaration lingering). With the file-level check,
    unloaded items no longer block revoke cleanup; bundles and items that did load the hook
    still keep the subscription.
    """

    async def test_item_plugin_not_loading_pattern_does_not_block_unload(
        self, app, tmp_path
    ) -> None:
        """beta item-approves only a skill (not the hook declaring note.created) -> after revoking bundle alpha, the subscription is clean."""
        root = tmp_path / "plugins"
        # Both plugins declare note.created (default on); alpha loads as a bundle, beta item-approves only a skill
        make_plugin(root, "alpha", hook_enabled=True)
        make_plugin(
            root,
            "beta",
            skills=("skills/b-notes",),
            hooks=("hooks/h-note.json",),
            mcp=None,
            hook_enabled=True,
        )
        await _approve(app, "alpha")
        await _approve_item(app, "beta", skills=["b-notes"])
        assert app.hooks.registered() == {"on_event": 1}
        assert app.hooks.event_patterns == ("note.created",)
        await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "alpha", "approved": False}
        )
        # alpha's hook is revoked and beta never checked that hook -> the pattern must not dangle
        assert app.hooks.registered() == {}
        assert app.hooks.event_patterns == ()

    async def test_item_plugin_loading_pattern_keeps_subscription(self, app, tmp_path) -> None:
        """beta item-approves the hook declaring note.created -> after revoking bundle alpha, the subscription is kept."""
        root = tmp_path / "plugins"
        make_plugin(root, "alpha", hook_enabled=True)
        make_plugin(
            root,
            "beta",
            skills=("skills/b-notes",),
            hooks=("hooks/h-note.json",),
            mcp=None,
            hook_enabled=True,
        )
        await _approve(app, "alpha")
        await _approve_item(app, "beta", skills=["b-notes"], hooks=["hooks/h-note.json"])
        assert app.hooks.registered() == {"on_event": 2}
        await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "alpha", "approved": False}
        )
        assert app.hooks.registered() == {"on_event": 1}  # beta's remains
        assert app.hooks.event_patterns == ("note.created",)  # subscription kept


class TestUserHookSubscriptionSymmetry:
    """The revoke subscription decision also consults user hooks (symmetric in both directions)."""

    async def test_unapprove_keeps_pattern_while_user_hook_declares(self, tmp_path) -> None:
        """A plugin and a user hook share note.created: revoking the plugin keeps the user-side subscription
        (both event_patterns and loop.patterns survive); unsubscription happens only after the user deletes
        the file and reloads; the revoked plugin's ownership records are dropped too, so no ghost source
        pins later decisions."""
        hooks_dir = tmp_path / "ws" / "hooks"
        hooks_dir.mkdir(parents=True)
        (hooks_dir / "u.json").write_text(
            json.dumps({"on": "note.created", "description": "user observed", "enabled": True}),
            encoding="utf-8",
        )
        make_plugin(tmp_path / "plugins", "example", skills=(), mcp=None, hook_enabled=True)
        app = build(tmp_path)
        try:
            await _approve(app)
            assert app.hooks.registered() == {"on_event": 2}
            # Revoke the plugin: the user hook still declares it -> subscription kept
            await execute(
                app.registry,
                "set_plugin_approval",
                USER_CTX,
                {"name": "example", "approved": False},
            )
            assert app.hooks.registered() == {"on_event": 1}
            assert "note.created" in app.hooks.event_patterns
            assert "note.created" in app.loop.patterns
            assert app.hooks.pattern_owner_sources("note.created") == ("user:u",)
            # Unsubscription only truly happens after the user deletes the file and reloads
            (hooks_dir / "u.json").unlink()
            await execute(app.registry, "reload_user_hooks", USER_CTX, {})
            assert "note.created" not in app.hooks.event_patterns
            assert "note.created" not in app.loop.patterns
        finally:
            app.memory.close()

    async def test_plugin_star_on_skipped_at_approve_and_rebuild(self, tmp_path) -> None:
        """A plugin hook declaring on: "*": approval loading skips the file (sync never crashes),
        and startup loading after a rebuild in the same state skips it too (EventLoop construction survives)."""
        make_plugin(
            tmp_path / "plugins",
            "example",
            skills=(),
            mcp=None,
            hook_specs={"hooks/on-note-created.json": {"on": "*", "enabled": True}},
        )
        app = build(tmp_path)
        try:
            out = await _approve(app)
            assert out["loaded"]["hooks"] == 0
            assert app.hooks.registered() == {}
            assert "*" not in app.hooks.event_patterns
        finally:
            app.memory.close()
        app2 = build(
            tmp_path
        )  # rebuild in the approved state: startup loading goes through the same loader checks
        try:
            assert app2.hooks.registered() == {}
            assert "*" not in app2.loop.patterns
        finally:
            app2.memory.close()


# ---- Runtime hook dynamic subscription (subscribe on approval / withdraw on revoke, no restart) ----


async def _run_loop_task(loop: EventLoop):
    task = asyncio.create_task(loop.run())
    for _ in range(100):  # run() backfills before subscribing; wait for assembly
        if loop._sub is not None:
            break
        await asyncio.sleep(0)
    await asyncio.sleep(0)  # ensure it is blocked in sub.get
    return task


class TestRunTimeSubscription:
    """Same process, no app rebuild: approve -> publish -> hook fires; revoke withdraws immediately."""

    async def _app_with_live_loop(self, tmp_path):
        """build_agent with an injected shared bus, plus a real loop.run() task; returns (app, bus, task).

        The injected bus = EventBus(events.db) carries the EventLoop push subscription, so publishes
        arrive directly. The empty EventLog created inside the app serves cursors (no history,
        empty backfill) and is closed manually after the test.
        """
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

    async def test_approve_then_publish_triggers_hook(self, tmp_path) -> None:
        """After approving a plugin with a domain-event hook, publishing that event in the same process fires the hook."""
        root = tmp_path / "plugins"
        make_plugin(root, "example", hook_enabled=True)  # on note.created
        app, bus, task = await self._app_with_live_loop(tmp_path)
        try:
            # Before approval: publish never enters the loop (no subscription)
            assert "note.created" not in app.loop.patterns
            await bus.publish(Event(type="note.created", actor=LOCAL_USER, payload={}))
            await asyncio.sleep(0)
            # After approval: the pattern enters the loop, and a further publish fires the hook (via on_event)
            await _approve(app, "example")
            assert "note.created" in app.loop.patterns  # subscribed without a restart
            seen: list[str] = []
            app.hooks.register(
                "on_event", lambda event, **kw: seen.append(event.type), source="test"
            )
            await bus.publish(Event(type="note.created", actor=LOCAL_USER, payload={}))
            await asyncio.sleep(0)
            assert seen == ["note.created"]  # actually fired
        finally:
            app.loop.stop()
            task.cancel()
            app.log.close()  # the empty EventLog created inside build_agent (owns_log=False)
            app.memory.close()

    async def test_unapprove_stops_trigger(self, tmp_path) -> None:
        """After revoking, events of that type no longer fire; other approved plugins sharing the pattern keep the subscription."""
        root = tmp_path / "plugins"
        make_plugin(root, "alpha", hook_enabled=True)  # note.created
        make_plugin(root, "beta", hook_enabled=True)  # note.created
        app, _bus, task = await self._app_with_live_loop(tmp_path)
        try:
            await _approve(app, "alpha")
            await _approve(app, "beta")
            assert app.loop.patterns.count("note.created") == 1  # deduplicated
            # Revoke alpha: beta still loads the same pattern -> the loop subscription is kept
            await execute(
                app.registry, "set_plugin_approval", USER_CTX, {"name": "alpha", "approved": False}
            )
            assert app.hooks.registered() == {"on_event": 1}
            assert "note.created" in app.loop.patterns  # beta remains, subscription not withdrawn
            # Revoke beta: nobody wants it -> the pattern exits the loop
            await execute(
                app.registry, "set_plugin_approval", USER_CTX, {"name": "beta", "approved": False}
            )
            assert "note.created" not in app.loop.patterns  # revoked means withdrawn
        finally:
            app.loop.stop()
            task.cancel()
            app.log.close()
            app.memory.close()

    async def test_run_time_sync_no_duplicate_dispatch(self, tmp_path) -> None:
        """A single event is never double-processed because of the dynamic subscription (push once; relay once)."""
        root = tmp_path / "plugins"
        make_plugin(root, "example", hook_enabled=True)
        app, bus, task = await self._app_with_live_loop(tmp_path)
        try:
            calls: list[str] = []
            app.hooks.register(
                "on_event", lambda event, **kw: calls.append(f"hook:{event.type}"), source="test"
            )
            await _approve(app, "example")
            # Manually sync once more (simulating idempotency): subscriptions never double
            app.loop.sync_extra_patterns(app.hooks.event_patterns)
            await bus.publish(Event(type="note.created", actor=LOCAL_USER, payload={}))
            await asyncio.sleep(0)
            assert calls == ["hook:note.created"]  # exactly once
        finally:
            app.loop.stop()
            task.cancel()
            app.log.close()  # the empty EventLog created inside build_agent (owns_log=False)
            app.memory.close()


# ---- Revocation / item deselection reclaims MCP entries registered by the plugin ----


class TestMcpReclaim:
    """MCP reclaim: only entries this plugin registered with no tools approved are reclaimed;
    manually added entries, entries with approved tools, entries other plugins still use, and
    entries whose config does not match are skipped and disclosed — never deleted by mistake."""

    async def test_unapprove_reclaims_registered_unused(self, app, tmp_path) -> None:
        make_plugin(tmp_path / "plugins", "example")
        await _approve(app)  # registers example-search with approved=[]
        out = await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "example", "approved": False}
        )
        assert out["approved"] is False
        assert out["mcp_reclaimed"] == ["example-search"]
        assert out["mcp_reclaim_skipped"] == []
        assert await execute(app.registry, "list_mcp_servers", USER_CTX, {}) == []

    async def test_unapprove_keeps_user_manual_mcp(self, app, tmp_path) -> None:
        """A manually added server not declared in the plugin manifest is unaffected by the plugin revoke."""
        make_plugin(tmp_path / "plugins", "example")
        await execute(
            app.registry,
            "add_mcp_server",
            USER_CTX,
            {"id": "manual-srv", "kind": "stdio", "command": "uvx"},
        )
        await _approve(app)
        out = await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "example", "approved": False}
        )
        assert out["mcp_reclaimed"] == ["example-search"]
        servers = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
        assert [s["id"] for s in servers] == ["manual-srv"]

    async def test_unapprove_skips_same_id_user_config(self, app, tmp_path) -> None:
        """Guard: same id but config differing from the plugin declaration (the user added it manually first) -> skipped and disclosed, not deleted."""
        make_plugin(tmp_path / "plugins", "example")  # mcp.json: npx -y x
        await execute(
            app.registry,
            "add_mcp_server",
            USER_CTX,
            {"id": "example-search", "kind": "stdio", "command": "npx"},
        )
        await _approve(app)  # same id already exists: registration skipped
        out = await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "example", "approved": False}
        )
        assert out["mcp_reclaimed"] == []
        assert [s["id"] for s in out["mcp_reclaim_skipped"]] == ["example-search"]
        assert out["mcp_reclaim_skipped"][0]["reason"]
        servers = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
        assert [s["id"] for s in servers] == ["example-search"]  # the manual config survives

    async def test_unapprove_invalid_declaration_skips_honestly(self, app, tmp_path) -> None:
        """An invalid declaration (necessarily skipped at registration) with a same-id config present (necessarily manual) -> honestly skipped, never deleted by mistake."""
        root = tmp_path / "plugins"
        d = make_plugin(root, "example")
        (d / "mcp.json").write_text(
            json.dumps({"servers": {"example-search": {"command": ""}}}), encoding="utf-8"
        )
        await execute(
            app.registry,
            "add_mcp_server",
            USER_CTX,
            {"id": "example-search", "kind": "stdio", "command": "npx"},
        )
        out = await _approve(app)
        assert (
            out["loaded"]["mcp_registered"] == 0
        )  # the invalid declaration was skipped at registration
        out = await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "example", "approved": False}
        )
        assert out["mcp_reclaimed"] == []
        (skip,) = out["mcp_reclaim_skipped"]
        assert skip["id"] == "example-search"
        assert "invalid" in skip["reason"]  # not the generic reclaim-failure fallback
        assert app.mcp.find_config("example-search") is not None

    async def test_unapprove_skips_when_tools_approved(self, app, tmp_path) -> None:
        """Tools already approved (an explicit user dependency) -> kept and disclosed; the list still clears without rollback."""
        make_plugin(tmp_path / "plugins", "example")
        await _approve(app)
        cfg = app.mcp.find_config("example-search")
        await app.mcp.upsert_config({**cfg, "approved": ["*"]}, LOCAL_USER)
        out = await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "example", "approved": False}
        )
        assert out["mcp_reclaimed"] == []
        assert [s["id"] for s in out["mcp_reclaim_skipped"]] == ["example-search"]
        assert app.mcp.find_config("example-search") is not None
        assert app.settings.get("agent.plugins.approved") == []

    async def test_unapprove_shared_server_waits_for_last_plugin(self, app, tmp_path) -> None:
        """Two plugins declaring the same server id: revoking one reclaims nothing; only revoking the last one does."""
        root = tmp_path / "plugins"
        shared = {"shared-search": {"command": "npx", "args": ["-y", "x"]}}
        make_plugin(root, "alpha", mcp_servers=shared)
        make_plugin(root, "beta", mcp_servers=shared)
        await _approve(app, "alpha")
        await _approve(app, "beta")
        await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "alpha", "approved": False}
        )
        assert app.mcp.find_config("shared-search") is not None  # beta still uses it
        out = await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "beta", "approved": False}
        )
        assert out["mcp_reclaimed"] == ["shared-search"]
        assert app.mcp.find_config("shared-search") is None

    async def test_item_deselect_reclaims_removed_mcp(self, app, tmp_path) -> None:
        """Deselecting an mcp id in an item approval follows the same safety rules as a bundle revoke; revoking clears the last one remaining."""
        make_two_of_each(tmp_path / "plugins")
        await _approve_item(app, "multi", skills=["alpha"], mcp=["multi-s1", "multi-s2"])
        out = await _approve_item(app, "multi", skills=["alpha"], mcp=["multi-s1"])
        assert out["mcp_reclaimed"] == ["multi-s2"]
        assert app.mcp.find_config("multi-s1") is not None
        out2 = await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "multi", "approved": False}
        )
        assert out2["mcp_reclaimed"] == ["multi-s1"]
        assert await execute(app.registry, "list_mcp_servers", USER_CTX, {}) == []

    async def test_unapprove_deleted_dir_reclaims_from_item_record(self, tmp_path) -> None:
        """Directory deleted but the item approval record still lists ids -> reclaim follows the record; the list still clears."""
        root = tmp_path / "plugins"
        make_two_of_each(root)
        app1 = build(tmp_path)
        try:
            await _approve_item(app1, "multi", mcp=["multi-s1", "multi-s2"])
        finally:
            app1.close()
        shutil.rmtree(root / "multi")
        app2 = build(tmp_path)
        try:
            out = await execute(
                app2.registry, "set_plugin_approval", USER_CTX, {"name": "multi", "approved": False}
            )
            assert sorted(out["mcp_reclaimed"]) == ["multi-s1", "multi-s2"]
            assert app2.settings.get("agent.plugins.approvals") == {}
            assert await execute(app2.registry, "list_mcp_servers", USER_CTX, {}) == []
        finally:
            app2.close()

    async def test_unapprove_deleted_dir_bundle_no_reclaim(self, tmp_path) -> None:
        """A bundle (legacy key) has no id record: after the directory is deleted, revoke only clears the list — no id guessing, no crash."""
        root = tmp_path / "plugins"
        make_plugin(root, "example")
        app1 = build(tmp_path)
        try:
            await _approve(app1)
        finally:
            app1.close()
        shutil.rmtree(root / "example")
        app2 = build(tmp_path)
        try:
            out = await execute(
                app2.registry,
                "set_plugin_approval",
                USER_CTX,
                {"name": "example", "approved": False},
            )
            assert out["mcp_reclaimed"] == []
            assert out["mcp_reclaim_skipped"] == []
            assert app2.settings.get("agent.plugins.approved") == []
        finally:
            app2.close()

    async def test_reclaim_failure_disclosed_not_rolled_back(
        self, app, tmp_path, monkeypatch
    ) -> None:
        """An error reclaiming one server -> recorded in skipped; the list still clears and the other ids reclaim as usual."""
        make_two_of_each(tmp_path / "plugins")
        await _approve_item(app, "multi", mcp=["multi-s1", "multi-s2"])
        real_delete = app.mcp.delete_config

        async def flaky_delete(sid: str, actor: object) -> None:
            if sid == "multi-s1":
                raise RuntimeError("disk broken")
            await real_delete(sid, actor)

        monkeypatch.setattr(app.mcp, "delete_config", flaky_delete)
        out = await execute(
            app.registry, "set_plugin_approval", USER_CTX, {"name": "multi", "approved": False}
        )
        assert out["mcp_reclaimed"] == ["multi-s2"]
        assert out["mcp_reclaim_skipped"] == [
            {"id": "multi-s1", "reason": "reclaim failed: disk broken"}
        ]
        assert app.settings.get("agent.plugins.approvals") == {}  # revocation never rolls back

    async def test_reclaim_uses_full_remove_path(self, tmp_path) -> None:
        """Reclaim = unmount + drop_session + delete_config (the same path as remove_mcp_server)."""

        class Session:
            def __init__(self) -> None:
                self.closed = False

            async def list_remote_tools(self) -> list[dict]:
                return []

            async def call_tool(self, name: str, arguments: dict) -> str:
                return ""

            async def aclose(self) -> None:
                self.closed = True

        sessions: dict[str, Session] = {}

        async def connect(cfg: dict) -> Session:
            s = Session()
            sessions[cfg["id"]] = s
            return s

        make_plugin(tmp_path / "plugins", "example")
        app = build(tmp_path, mcp_connect=connect)
        try:
            await _approve(app)
            await execute(app.registry, "preview_mcp_tools", USER_CTX, {"id": "example-search"})
            assert "example-search" in sessions  # the session was opened
            out = await execute(
                app.registry,
                "set_plugin_approval",
                USER_CTX,
                {"name": "example", "approved": False},
            )
            assert out["mcp_reclaimed"] == ["example-search"]
            assert sessions["example-search"].closed  # drop_session actually ran
            assert app.mcp.find_config("example-search") is None
            assert not [n for n in app.spawner._toolbelt.names() if n.startswith("mcp__")]
        finally:
            app.close()


# ---- zip / directory install wizard (the step before discovery) ----


def build_plugin_src(tmp_path: Path, name: str = "example", **kw) -> Path:
    """Builds a plugin source directory under workspace/src (for zip / directory installs, inside allowed roots)."""
    return make_plugin(tmp_path / "ws" / "src", name, **kw)


def zip_dir(src: Path, zip_path: Path, *, prefix: str = "") -> Path:
    """Zips a directory; prefix controls the root layout ("pkg/" = single top-level directory layout)."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(src.rglob("*")):
            if p.is_file():
                zf.write(p, prefix + p.relative_to(src).as_posix())
    return zip_path


async def _install(app, **args) -> dict:
    return await execute(app.registry, "install_plugin", USER_CTX, args)


def plugin_names(app) -> list[str]:
    return [i["name"] for i in app.plugins.list()]


class TestInstallZip:
    """Zip install contract, root-layout conventions, and the existing approval chain after install."""

    async def test_zip_root_layout_contract(self, app, tmp_path) -> None:
        src = build_plugin_src(tmp_path)
        z = zip_dir(src, tmp_path / "ws" / "imports" / "example.zip")
        out = await _install(app, zip_path=str(z))
        assert out == {
            "name": "example",
            "version": "0.1.0",
            "path": "example",
            "permissions": {"scopes": ["notes.write"], "network": "off", "fs": "none"},
            "contains_summary": {"skills": 1, "hooks": 1, "mcp": True},
        }
        assert (tmp_path / "plugins" / "example" / "plugin.json").is_file()
        items = app.plugins.list()
        assert [i["name"] for i in items] == ["example"]
        assert items[0]["approved"] is False  # installing never auto-approves

    async def test_zip_then_approve_full_cycle(self, app, tmp_path) -> None:
        """Install -> visible in list -> the existing bundle approval loads it (the wizard closed loop)."""
        src = build_plugin_src(tmp_path, hook_enabled=True)
        z = zip_dir(src, tmp_path / "ws" / "example.zip")
        await _install(app, zip_path=str(z))
        out = await _approve(app, "example")
        assert out["approved"] is True
        assert "daily-note" in [e["name"] for e in app.skills.index()]

    async def test_zip_single_toplevel_dir_layout(self, app, tmp_path) -> None:
        src = build_plugin_src(tmp_path)
        z = zip_dir(src, tmp_path / "ws" / "pkg.zip", prefix="pkg/")
        out = await _install(app, zip_path=str(z))
        assert out["name"] == "example" and out["path"] == "example"

    async def test_zip_no_manifest_rejected(self, app, tmp_path) -> None:
        d = tmp_path / "ws" / "plain"
        d.mkdir(parents=True)
        (d / "readme.txt").write_text("not a plugin", encoding="utf-8")
        z = zip_dir(d, tmp_path / "ws" / "plain.zip")
        with pytest.raises(ServiceError) as exc:
            await _install(app, zip_path=str(z))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert plugin_names(app) == []  # nothing landed on disk

    async def test_zip_two_toplevel_dirs_rejected(self, app, tmp_path) -> None:
        d = tmp_path / "ws" / "amb"
        (d / "one").mkdir(parents=True)
        (d / "one" / "plugin.json").write_text('{"name": "one"}', encoding="utf-8")
        (d / "two").mkdir()
        (d / "two" / "plugin.json").write_text('{"name": "two"}', encoding="utf-8")
        z = zip_dir(d, tmp_path / "ws" / "amb.zip")
        with pytest.raises(ServiceError) as exc:
            await _install(app, zip_path=str(z))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert plugin_names(app) == []

    async def test_zip_bad_manifest_rejected(self, app, tmp_path) -> None:
        src = build_plugin_src(tmp_path)
        (src / "plugin.json").write_text("{bad", encoding="utf-8")
        z = zip_dir(src, tmp_path / "ws" / "bad.zip")
        with pytest.raises(ServiceError) as exc:
            await _install(app, zip_path=str(z))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert plugin_names(app) == []

    async def test_zip_contains_escape_rejected(self, app, tmp_path) -> None:
        """A contains escape -> the whole install is refused up front (the jail validates proactively), never landing broken content on disk."""
        src = build_plugin_src(
            tmp_path, "escapee", skills=("../outside/skill-a",), hooks=(), mcp=None
        )
        z = zip_dir(src, tmp_path / "ws" / "escapee.zip")  # packs only the plugin directory itself
        with pytest.raises(ServiceError) as exc:
            await _install(app, zip_path=str(z))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert "outside" in exc.value.body.message
        assert plugin_names(app) == []

    async def test_zip_slip_rejected_whole(self, app, tmp_path) -> None:
        """../ and absolute-path entries -> the whole install aborts; no files outside the root and no plugins/ residue."""
        z = tmp_path / "ws" / "evil.zip"
        z.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("../evil.txt", "escape content")
            zf.writestr("/abs/evil.txt", "absolute path")
            zf.writestr("plugin.json", json.dumps({"name": "slippery"}))
        with pytest.raises(ServiceError) as exc:
            await _install(app, zip_path=str(z))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert not (tmp_path / "evil.txt").exists()
        assert plugin_names(app) == []

    async def test_empty_zip_rejected(self, app, tmp_path) -> None:
        """An empty zip: a readable INVALID_INPUT rather than INTERNAL (the extraction root needs creating first)."""
        z = tmp_path / "ws" / "empty.zip"
        z.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z, "w"):
            pass
        with pytest.raises(ServiceError) as exc:
            await _install(app, zip_path=str(z))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert plugin_names(app) == []

    async def test_zip_over_limits(self, app, tmp_path, monkeypatch) -> None:
        """The three zip limits (total bytes / file count / single file) with constants injected to pin behavior."""
        from agent.plugins import install as install_mod

        src = build_plugin_src(tmp_path)
        z = zip_dir(src, tmp_path / "ws" / "big.zip")
        monkeypatch.setattr(install_mod, "MAX_ZIP_BYTES", 4)  # the real zip exceeds 4 bytes
        with pytest.raises(ServiceError) as exc:
            await _install(app, zip_path=str(z))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert plugin_names(app) == []

        d = tmp_path / "ws" / "many"
        d.mkdir(parents=True)
        for i in range(3):
            (d / f"f{i}.txt").write_text("x", encoding="utf-8")
        z2 = zip_dir(d, tmp_path / "ws" / "many.zip")
        monkeypatch.setattr(install_mod, "MAX_FILES", 2)
        with pytest.raises(ServiceError) as exc:
            await _install(app, zip_path=str(z2))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert plugin_names(app) == []

        d2 = tmp_path / "ws" / "fat"
        d2.mkdir(parents=True)
        (d2 / "fat.bin").write_bytes(b"x" * 16)
        z3 = zip_dir(d2, tmp_path / "ws" / "fat.zip")
        monkeypatch.setattr(install_mod, "MAX_FILE_BYTES", 8)
        with pytest.raises(ServiceError) as exc:
            await _install(app, zip_path=str(z3))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert plugin_names(app) == []


class TestInstallDir:
    """Directory install copies rather than moves; sources must be inside allowed roots (workspace / read_roots); sources are validated."""

    async def test_dir_install_copies_not_moves(self, app, tmp_path) -> None:
        src = build_plugin_src(tmp_path)
        out = await _install(app, source_dir=str(src))
        assert out["name"] == "example"
        assert src.exists()  # copied, not moved
        assert plugin_names(app) == ["example"]

    async def test_dir_outside_roots_rejected_then_read_root_ok(self, app, tmp_path) -> None:
        """Sources outside allowed roots are refused; after configuring read_roots the same source installs (sources may live outside the workspace)."""
        outside = make_plugin(tmp_path / "outside", "faraway")
        with pytest.raises(ServiceError) as exc:
            await _install(app, source_dir=str(outside))
        assert exc.value.body.code == "AGENT.FORBIDDEN"
        assert plugin_names(app) == []
        await execute(
            app.registry,
            "set_setting",
            USER_CTX,
            {"key": "agent.fs.read_roots", "value": [str(tmp_path / "outside")]},
        )
        out = await _install(app, source_dir=str(outside))
        assert out["name"] == "faraway"
        assert outside.exists()  # still a copy

    async def test_relative_path_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await _install(app, source_dir="src/example")
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    async def test_missing_source_or_manifest_rejected(self, app, tmp_path) -> None:
        with pytest.raises(ServiceError) as exc:
            await _install(app, source_dir=str(tmp_path / "ws" / "ghost"))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        empty = tmp_path / "ws" / "empty"
        empty.mkdir(parents=True)
        with pytest.raises(ServiceError) as exc:
            await _install(app, source_dir=str(empty))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert plugin_names(app) == []

    async def test_symlink_in_source_rejected(self, app, tmp_path) -> None:
        """Symlinks inside the source are refused (preventing out-of-root content being copied into plugins/)."""
        src = build_plugin_src(tmp_path)
        target = tmp_path / "ws" / "secret.txt"
        target.write_text("secret", encoding="utf-8")
        try:
            os.symlink(target, src / "link.txt")
        except OSError:
            pytest.skip("no symlink permission in this environment")
        with pytest.raises(ServiceError) as exc:
            await _install(app, source_dir=str(src))
        assert exc.value.body.code == "AGENT.FORBIDDEN"
        assert plugin_names(app) == []


class TestInstallConflicts:
    """Conflicts are refused by default; an explicit overwrite is required; approved plugins are never overwritten."""

    async def test_conflict_requires_overwrite(self, app, tmp_path) -> None:
        src = build_plugin_src(tmp_path)
        await _install(app, source_dir=str(src))
        with pytest.raises(ServiceError) as exc:
            await _install(app, source_dir=str(src))
        assert exc.value.body.code == "AGENT.CONFLICT"

    async def test_overwrite_replaces_content(self, app, tmp_path) -> None:
        src = build_plugin_src(tmp_path, version="0.1.0")
        await _install(app, source_dir=str(src))
        newer = make_plugin(tmp_path / "ws" / "src2", version="0.2.0")
        out = await _install(app, source_dir=str(newer), overwrite=True)
        assert out["version"] == "0.2.0"
        assert plugin_names(app) == ["example"]  # a single identity, never duplicated

    async def test_overwrite_approved_plugin_rejected(self, app, tmp_path) -> None:
        """An approved plugin is refused even with overwrite=true (revoke approval first); its content is untouched."""
        src = build_plugin_src(tmp_path, version="0.1.0")
        await _install(app, source_dir=str(src))
        await _approve(app, "example")
        newer = make_plugin(tmp_path / "ws" / "src2", version="0.2.0")
        with pytest.raises(ServiceError) as exc:
            await _install(app, source_dir=str(newer), overwrite=True)
        assert exc.value.body.code == "AGENT.CONFLICT"
        item = app.plugins.list()[0]
        assert item["version"] == "0.1.0" and item["approved"] is True

    async def test_source_same_as_dest_rejected(self, app, tmp_path) -> None:
        """A source directory identical to the installed destination itself is refused (otherwise place would wipe dest = source first, destroying the data).

        The plugins root is not in the allowed roots by default, so the root is added to read_roots
        first to make the path reachable (defense in depth for when plugins_dir is configured
        inside the workspace or an extra root).
        """
        src = build_plugin_src(tmp_path)
        await _install(app, source_dir=str(src))
        dest = tmp_path / "plugins" / "example"
        await execute(
            app.registry,
            "set_setting",
            USER_CTX,
            {"key": "agent.fs.read_roots", "value": [str(tmp_path / "plugins")]},
        )
        with pytest.raises(ServiceError) as exc:
            await _install(app, source_dir=str(dest), overwrite=True)
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert (dest / "plugin.json").is_file()  # the source (the destination itself) was not wiped
        assert plugin_names(app) == ["example"]

    async def test_alias_dir_same_name_conflict(self, app, tmp_path) -> None:
        """Same plugin name under a different directory name (e.g. a `_` alias directory) still conflicts; overwriting removes the old directory."""
        make_plugin(
            tmp_path / "plugins", "aliasdir", raw_manifest={"name": "clash", "version": "0.0.1"}
        )
        src = make_plugin(tmp_path / "ws" / "src", "clash")
        with pytest.raises(ServiceError) as exc:
            await _install(app, source_dir=str(src))
        assert exc.value.body.code == "AGENT.CONFLICT"
        out = await _install(app, source_dir=str(src), overwrite=True)
        assert out["path"] == "clash"
        assert not (tmp_path / "plugins" / "aliasdir").exists()
        assert plugin_names(app) == ["clash"]


class TestInstallSemantics:
    """Failures never leave half installs, nothing auto-approves, `_`-prefixed names install fine, USER-only."""

    async def test_agent_actor_installs_but_never_approves(self, app, tmp_path) -> None:
        """Parity: the agent may install/uninstall (the L2 gate lives on its tool
        side); approval stays user-only because it writes a user_only setting."""
        src = build_plugin_src(tmp_path)
        await execute(app.registry, "install_plugin", AGENT_CTX, {"source_dir": str(src)})
        assert plugin_names(app) == ["example"]
        assert app.settings.get("agent.plugins.approved") == []
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry,
                "set_plugin_approval",
                AGENT_CTX,
                {"name": "example", "approved": True},
            )
        assert exc.value.body.code == "AGENT.FORBIDDEN"
        await execute(app.registry, "uninstall_plugin", AGENT_CTX, {"name": "example"})
        assert plugin_names(app) == []

    async def test_no_actor_auth_required(self, app, tmp_path) -> None:
        src = build_plugin_src(tmp_path)
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "install_plugin", None, {"source_dir": str(src)})
        assert exc.value.body.code == "CAPABILITY.AUTH_REQUIRED"

    async def test_install_not_auto_approved_anything(self, app, tmp_path) -> None:
        """No approval, no loading: no skill in the index, no hook registered, no MCP registered."""
        src = build_plugin_src(tmp_path, hook_enabled=True)
        await _install(app, source_dir=str(src))
        assert "daily-note" not in [e["name"] for e in app.skills.index()]
        assert app.hooks.registered() == {}
        assert await execute(app.registry, "list_mcp_servers", USER_CTX, {}) == []

    async def test_copy_failure_leaves_no_half_install(self, app, tmp_path, monkeypatch) -> None:
        """A failure mid-write -> the destination directory is rolled back and emptied."""
        import agent.plugins.installer as installer_mod

        src = build_plugin_src(tmp_path)
        dest = tmp_path / "plugins" / "example"

        def boom(plugin_root: Path, target: Path) -> None:
            target.mkdir(parents=True)
            (target / "half.txt").write_text("half", encoding="utf-8")
            raise RuntimeError("disk exploded")

        monkeypatch.setattr(installer_mod, "place_plugin", boom)
        with pytest.raises(RuntimeError):
            await _install(app, source_dir=str(src))
        assert not dest.exists()
        assert plugin_names(app) == []

    async def test_both_sources_or_neither_rejected(self, app, tmp_path) -> None:
        src = build_plugin_src(tmp_path)
        z = zip_dir(src, tmp_path / "ws" / "x.zip")
        with pytest.raises(ServiceError) as exc:
            await _install(app, zip_path=str(z), source_dir=str(src))
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        with pytest.raises(ServiceError) as exc:
            await _install(app)
        assert exc.value.body.code == "AGENT.INVALID_INPUT"

    async def test_underscore_name_installable(self, app, tmp_path) -> None:
        """`_`-prefixed names install as usual (consistent with discovery semantics)."""
        src = build_plugin_src(tmp_path, "_dashed")
        out = await _install(app, source_dir=str(src))
        assert out["name"] == "_dashed" and out["path"] == "_dashed"
        assert plugin_names(app) == ["_dashed"]


class TestUninstall:
    """Only unapproved plugin directories are deleted; approved ones must be revoked first; unknown names give NOT_FOUND."""

    async def test_uninstall_removes_installed_dir(self, app, tmp_path) -> None:
        src = build_plugin_src(tmp_path)
        await _install(app, source_dir=str(src))
        out = await execute(app.registry, "uninstall_plugin", USER_CTX, {"name": "example"})
        assert out == {"name": "example", "uninstalled": True, "path": "example"}
        assert not (tmp_path / "plugins" / "example").exists()
        assert plugin_names(app) == []
        assert src.exists()  # the original source directory is untouched

    async def test_uninstall_approved_rejected(self, app, tmp_path) -> None:
        src = build_plugin_src(tmp_path)
        await _install(app, source_dir=str(src))
        await _approve(app, "example")
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "uninstall_plugin", USER_CTX, {"name": "example"})
        assert exc.value.body.code == "AGENT.CONFLICT"
        assert (tmp_path / "plugins" / "example" / "plugin.json").is_file()

    async def test_uninstall_symlinked_dir_rejected(self, app, tmp_path) -> None:
        """The plugin directory itself is a symlink: refused (deleting through the link would destroy the target's content tree)."""
        real = make_plugin(tmp_path / "outside", "linked")
        link = tmp_path / "plugins" / "linked"
        try:
            os.symlink(real, link, target_is_directory=True)
        except OSError:
            pytest.skip("no symlink permission in this environment")
        assert app.plugins.find("linked") is not None  # discovery sees it through the link
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "uninstall_plugin", USER_CTX, {"name": "linked"})
        assert exc.value.body.code == "AGENT.INVALID_INPUT"
        assert real.is_dir()  # the link target is preserved intact

    async def test_uninstall_unknown_not_found(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "uninstall_plugin", USER_CTX, {"name": "ghost"})
        assert exc.value.body.code == "AGENT.NOT_FOUND"
