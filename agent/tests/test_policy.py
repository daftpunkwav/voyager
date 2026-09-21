"""Tests for the four policy dimensions: network, fs, app, and shell."""

from agent.policy import (
    Action,
    AppPolicy,
    FsPolicy,
    Level,
    NetworkPolicy,
    PolicyEngine,
    narrow_network,
)


class TestNetwork:
    def test_off_denies_all(self) -> None:
        engine = PolicyEngine(network=NetworkPolicy(mode="off"))
        d = engine.decide(Action(dimension="network", target="https://github.com/x"))
        assert not d.allow
        assert "off" in d.reason

    def test_whitelist_suffix_match(self) -> None:
        engine = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=("github.com",)))
        assert engine.decide(Action(dimension="network", target="https://api.github.com/x")).allow
        d = engine.decide(Action(dimension="network", target="https://evil.com/x"))
        assert not d.allow
        assert "allowlist" in d.reason

    def test_all_allows_with_notify(self) -> None:
        engine = PolicyEngine(network=NetworkPolicy(mode="all"))
        d = engine.decide(Action(dimension="network", target="https://example.com"))
        assert d.allow and d.level == Level.L1_NOTIFY

    def test_all_rejects_nonglobal_literals(self) -> None:
        """Even the ALL tier refuses loopback/link-local/private-network literals (SSRF); the reason explains why."""
        engine = PolicyEngine(network=NetworkPolicy(mode="all"))
        for target in (
            "http://127.0.0.1/",  # loopback
            "http://localhost:8080/",  # local hostname
            "http://169.254.169.254/",  # link-local / cloud metadata
            "http://10.0.0.1/",  # private network
        ):
            d = engine.decide(Action(dimension="network", target=target))
            assert not d.allow, target
            assert "loopback" in d.reason or "private" in d.reason, target

    def test_nonglobal_beats_whitelist(self) -> None:
        """Non-global checks precede the whitelist: a loopback IP listed in the whitelist is still refused."""
        engine = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=("127.0.0.1",)))
        d = engine.decide(Action(dimension="network", target="http://127.0.0.1/"))
        assert not d.allow
        assert "loopback" in d.reason or "private" in d.reason

    def test_userinfo_url_judged_by_real_host(self) -> None:
        """A userinfo URL like https://github.com@evil.com/ actually connects to evil.com and must be refused;
        the reverse https://evil.com@github.com/ connects to github.com (host parsing looks only after the @)."""
        engine = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=("github.com",)))
        d = engine.decide(Action(dimension="network", target="https://github.com@evil.com/x"))
        assert not d.allow and "evil.com" in d.reason
        assert engine.decide(
            Action(dimension="network", target="https://evil.com@github.com/x")
        ).allow

    def test_port_does_not_break_match(self) -> None:
        engine = PolicyEngine(network=NetworkPolicy(mode="whitelist", domains=("github.com",)))
        assert engine.decide(Action(dimension="network", target="https://github.com:8443/x")).allow


class TestFs:
    def test_inside_jail(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        inside = tmp_path / "a.txt"
        inside.touch()
        d = engine.decide(Action(dimension="fs", target=str(inside), write=True))
        assert d.allow and d.level == Level.L1_NOTIFY  # write -> notify

    def test_outside_jail_denied(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)))
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "evil.txt")))
        assert not d.allow
        assert "outside the working directory" in d.reason

    def test_delete_needs_confirm(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        target = tmp_path / "a.txt"
        d = engine.decide(Action(dimension="fs", target=str(target), irreversible=True))
        assert d.allow and d.level == Level.L2_CONFIRM


class TestFsSkillsGuard:
    """The skills/ subtree inside the jail is read-only for write/delete fs actions: refusal precedes L2."""

    def test_write_into_skills_denied(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        d = engine.decide(
            Action(dimension="fs", target=str(tmp_path / "skills" / "pwn" / "SKILL.md"), write=True)
        )
        assert not d.allow
        assert "skill directory" in d.reason

    def test_load_skills_still_allowed(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        d = engine.decide(
            Action(dimension="fs", target=str(tmp_path / "skills" / "pwn" / "SKILL.md"))
        )
        assert d.allow and d.level == Level.L0_SILENT

    def test_write_repo_still_allowed(self, tmp_path) -> None:
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        d = engine.decide(
            Action(dimension="fs", target=str(tmp_path / "repo" / "a.md"), write=True)
        )
        assert d.allow and d.level == Level.L1_NOTIFY

    def test_delete_skills_denied_before_confirm(self, tmp_path) -> None:
        """An irreversible action on skills is refused outright, never reaching the L2 confirmation."""
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path),)))
        d = engine.decide(
            Action(
                dimension="fs",
                target=str(tmp_path / "skills" / "keep" / "SKILL.md"),
                irreversible=True,
            )
        )
        assert not d.allow


class TestFsReadRoots:
    """Extra read-only roots (fs dimension): reads pass at L0, writes/deletes are always refused."""

    def test_read_inside_read_root_allowed(self, tmp_path) -> None:
        read_root = tmp_path / "docs"
        (read_root / "sub").mkdir(parents=True)
        engine = PolicyEngine(
            fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(read_root),))
        )
        d = engine.decide(Action(dimension="fs", target=str(read_root / "sub" / "a.txt")))
        assert d.allow and d.level == Level.L0_SILENT

    def test_read_root_itself_readable(self, tmp_path) -> None:
        engine = PolicyEngine(
            fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(tmp_path / "docs"),))
        )
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "docs")))
        assert d.allow and d.level == Level.L0_SILENT

    def test_write_in_read_root_denied(self, tmp_path) -> None:
        read_root = tmp_path / "docs"
        read_root.mkdir()
        engine = PolicyEngine(
            fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(read_root),))
        )
        d = engine.decide(Action(dimension="fs", target=str(read_root / "a.txt"), write=True))
        assert not d.allow
        assert "read-only" in d.reason

    def test_delete_in_read_root_denied_before_confirm(self, tmp_path) -> None:
        """Deletes on extra roots skip L2 confirmation entirely — confirming would grant no write permission, so refuse directly."""
        read_root = tmp_path / "docs"
        read_root.mkdir()
        engine = PolicyEngine(
            fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(read_root),))
        )
        d = engine.decide(
            Action(dimension="fs", target=str(read_root / "a.txt"), irreversible=True)
        )
        assert not d.allow
        assert "read-only" in d.reason

    def test_outside_all_roots_still_denied(self, tmp_path) -> None:
        engine = PolicyEngine(
            fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(tmp_path / "docs"),))
        )
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "evil.txt")))
        assert not d.allow
        assert "outside the working directory" in d.reason

    def test_workspace_write_unaffected_by_read_roots(self, tmp_path) -> None:
        """Workspace semantics regression: roots take precedence; extra roots never make the workspace read-only."""
        ws = tmp_path / "ws"
        engine = PolicyEngine(fs=FsPolicy(roots=(str(ws),), read_roots=(str(tmp_path),)))
        d = engine.decide(Action(dimension="fs", target=str(ws / "a.txt"), write=True))
        assert d.allow and d.level == Level.L1_NOTIFY

    def test_read_root_without_roots_rejected(self, tmp_path) -> None:
        """Without extra roots configured the behavior is unchanged: everything outside the workspace is refused."""
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)))
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "docs" / "a.txt")))
        assert not d.allow

    def test_relative_path_resolved_against_workspace_not_read_roots(self, tmp_path) -> None:
        """Relative paths resolve against the jail root only (matching the fs tools), never against extra roots:
        if a.txt resolved under the extra root the write would be refused; resolving via the workspace allows L1."""
        read_root = tmp_path / "docs"
        read_root.mkdir()
        ws = tmp_path / "ws"
        engine = PolicyEngine(fs=FsPolicy(roots=(str(ws),), read_roots=(str(read_root),)))
        d = engine.decide(Action(dimension="fs", target="a.txt", write=True))
        assert d.allow and d.level == Level.L1_NOTIFY

    def test_escape_via_dotdot_lands_in_read_root_readonly(self, tmp_path) -> None:
        """`..` escapes are judged by the resolved landing spot: ws/../docs/x resolves into the extra root -> read-only."""
        read_root = tmp_path / "docs"
        read_root.mkdir()
        engine = PolicyEngine(
            fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(read_root),))
        )
        inside = engine.decide(
            Action(dimension="fs", target=str(tmp_path / "ws" / ".." / "docs" / "a.txt"))
        )
        assert inside.allow and inside.level == Level.L0_SILENT
        write = engine.decide(
            Action(
                dimension="fs", target=str(tmp_path / "ws" / ".." / "docs" / "a.txt"), write=True
            )
        )
        assert not write.allow


class TestHotFsReadRootSettings:
    """Hot reads for extra read-only roots: without settings the construction snapshot is used; with settings, live reads."""

    def test_settings_override_construction_snapshot(self, tmp_path) -> None:
        read_root = tmp_path / "docs"
        read_root.mkdir()
        settings = _FakeSettings({"agent.fs.read_roots": [str(read_root)]})
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)), settings=settings)
        d = engine.decide(Action(dimension="fs", target=str(read_root / "a.txt")))
        assert d.allow and d.level == Level.L0_SILENT
        assert not engine.decide(
            Action(dimension="fs", target=str(read_root / "a.txt"), write=True)
        ).allow

    def test_invalid_settings_falls_back_to_snapshot(self, tmp_path) -> None:
        """A bad value (non-string-list) falls back to the snapshot wholesale instead of treating the bad setting as deny-all and crippling file reads."""
        settings = _FakeSettings({"agent.fs.read_roots": "not-a-list"})
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)), settings=settings)
        assert not engine.decide(
            Action(dimension="fs", target=str(tmp_path / "docs" / "a.txt"))
        ).allow

    def test_none_settings_value_keeps_snapshot(self, tmp_path) -> None:
        """When settings lacks the key (None), the construction snapshot is kept, same semantics as network hot reads."""
        engine = PolicyEngine(
            fs=FsPolicy(roots=(str(tmp_path / "ws"),), read_roots=(str(tmp_path / "docs"),)),
            settings=_FakeSettings({}),
        )
        assert engine.decide(Action(dimension="fs", target=str(tmp_path / "docs" / "a.txt"))).allow


class TestFsWriteRoots:
    """Extra read-write roots: reads L0, writes/deletes L2; workspace takes precedence and
    read_roots remain read-only as fallback — decision order roots -> write_roots -> read_roots -> refuse."""

    def _engine(self, tmp_path, *, write_roots=(), read_roots=()) -> PolicyEngine:
        return PolicyEngine(
            fs=FsPolicy(
                roots=(str(tmp_path / "ws"),),
                read_roots=tuple(read_roots),
                write_roots=tuple(write_roots),
            )
        )

    def test_read_inside_write_root_l0(self, tmp_path) -> None:
        write_root = tmp_path / "proj"
        (write_root / "sub").mkdir(parents=True)
        engine = self._engine(tmp_path, write_roots=(str(write_root),))
        d = engine.decide(Action(dimension="fs", target=str(write_root / "sub" / "a.txt")))
        assert d.allow and d.level == Level.L0_SILENT

    def test_write_inside_write_root_l2_not_l1(self, tmp_path) -> None:
        """Writes into user directories are not the workspace L1 notify; they require L2 confirmation."""
        write_root = tmp_path / "proj"
        write_root.mkdir()
        engine = self._engine(tmp_path, write_roots=(str(write_root),))
        d = engine.decide(Action(dimension="fs", target=str(write_root / "a.txt"), write=True))
        assert d.allow and d.level == Level.L2_CONFIRM
        assert "confirmation" in d.reason

    def test_delete_inside_write_root_l2(self, tmp_path) -> None:
        write_root = tmp_path / "proj"
        write_root.mkdir()
        engine = self._engine(tmp_path, write_roots=(str(write_root),))
        d = engine.decide(
            Action(dimension="fs", target=str(write_root / "a.txt"), irreversible=True)
        )
        assert d.allow and d.level == Level.L2_CONFIRM

    def test_write_in_read_root_only_still_denied(self, tmp_path) -> None:
        """Inside a read_root but not a write_root -> writes are still refused (write roots never relax read-only roots)."""
        read_root = tmp_path / "docs"
        read_root.mkdir()
        engine = self._engine(
            tmp_path, read_roots=(str(read_root),), write_roots=(str(tmp_path / "proj"),)
        )
        d = engine.decide(Action(dimension="fs", target=str(read_root / "a.txt"), write=True))
        assert not d.allow
        assert "read-only" in d.reason

    def test_workspace_precedence_over_write_roots(self, tmp_path) -> None:
        """Workspace precedence: paths inside the workspace nested under a write_root still follow workspace rules (write L1)."""
        write_root = tmp_path / "proj"
        ws = write_root / "ws"
        engine = PolicyEngine(fs=FsPolicy(roots=(str(ws),), write_roots=(str(write_root),)))
        d = engine.decide(Action(dimension="fs", target=str(ws / "a.txt"), write=True))
        assert d.allow and d.level == Level.L1_NOTIFY

    def test_workspace_skills_guard_not_relaxed_by_write_roots(self, tmp_path) -> None:
        """Pointing write_root at workspace/skills cannot bypass the write ban: the roots loop matches first and refuses."""
        ws = tmp_path / "ws"
        engine = PolicyEngine(fs=FsPolicy(roots=(str(ws),), write_roots=(str(ws / "skills"),)))
        d = engine.decide(
            Action(dimension="fs", target=str(ws / "skills" / "pwn" / "SKILL.md"), write=True)
        )
        assert not d.allow
        assert "skill directory" in d.reason

    def test_outside_all_roots_still_denied(self, tmp_path) -> None:
        engine = self._engine(tmp_path, write_roots=(str(tmp_path / "proj"),))
        d = engine.decide(Action(dimension="fs", target=str(tmp_path / "evil.txt")))
        assert not d.allow
        assert "outside the working directory" in d.reason


class TestHotFsWriteRootSettings:
    """Hot reads for extra read-write roots follow the read_roots pattern: with settings, live reads;
    missing keys / bad values fall back to the construction snapshot."""

    def test_settings_override_construction_snapshot(self, tmp_path) -> None:
        write_root = tmp_path / "proj"
        write_root.mkdir()
        settings = _FakeSettings({"agent.fs.write_roots": [str(write_root)]})
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)), settings=settings)
        d = engine.decide(Action(dimension="fs", target=str(write_root / "a.txt"), write=True))
        assert d.allow and d.level == Level.L2_CONFIRM
        r = engine.decide(Action(dimension="fs", target=str(write_root / "a.txt")))
        assert r.allow and r.level == Level.L0_SILENT

    def test_invalid_settings_falls_back_to_snapshot(self, tmp_path) -> None:
        """A bad value (non-string-list) falls back to the snapshot wholesale instead of treating the bad setting as deny-all and crippling the file tools."""
        settings = _FakeSettings({"agent.fs.write_roots": "not-a-list"})
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)), settings=settings)
        assert not engine.decide(
            Action(dimension="fs", target=str(tmp_path / "proj" / "a.txt"))
        ).allow

    def test_none_settings_value_keeps_snapshot(self, tmp_path) -> None:
        """When settings lacks the key (None), the construction snapshot is kept, same semantics as read_roots hot reads."""
        write_root = tmp_path / "proj"
        write_root.mkdir()
        engine = PolicyEngine(
            fs=FsPolicy(roots=(str(tmp_path / "ws"),), write_roots=(str(write_root),)),
            settings=_FakeSettings({}),
        )
        d = engine.decide(Action(dimension="fs", target=str(write_root / "a.txt"), write=True))
        assert d.allow and d.level == Level.L2_CONFIRM


class TestApp:
    def test_whitelist_and_denied(self) -> None:
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset({"set_theme"}), denied=frozenset()))
        assert engine.decide(Action(dimension="app", target="set_theme")).allow
        assert not engine.decide(Action(dimension="app", target="delete_note")).allow

    def test_denied_beats_wildcard(self) -> None:
        engine = PolicyEngine(
            app=AppPolicy(allowed=frozenset({"*"}), denied=frozenset({"danger_op"}))
        )
        assert not engine.decide(Action(dimension="app", target="danger_op")).allow

    def test_prefix_denied(self) -> None:
        engine = PolicyEngine(
            app=AppPolicy(allowed=frozenset({"*"}), denied=frozenset({"notes__*"}))
        )
        assert not engine.decide(Action(dimension="app", target="notes__create_note")).allow
        assert engine.decide(Action(dimension="app", target="graph__search")).allow

    def test_prefix_allowed(self) -> None:
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset({"notes__*"})))
        assert engine.decide(Action(dimension="app", target="notes__create_note")).allow
        assert not engine.decide(Action(dimension="app", target="graph__search")).allow

    def test_irreversible_confirm(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="app", target="delete_note", irreversible=True))
        assert d.allow and d.level == Level.L2_CONFIRM

    def test_empty_allowed_denies_all(self) -> None:
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset()))
        assert not engine.decide(Action(dimension="app", target="notes__create_note")).allow


class TestShell:
    def test_shell_default_confirm(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="shell", target="rm -rf x"))
        assert d.allow and d.level == Level.L2_CONFIRM

    def test_none_dimension_passthrough(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="none"))
        assert d.allow and d.level == Level.L0_SILENT


class TestShellSkillsGuard:
    """run_shell commands clearly writing/deleting the skills subtree are refused outright, ahead of L2."""

    def test_redirect_into_skills_denied(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="shell", target="echo x > skills/pwn.txt", write=True))
        assert not d.allow
        assert "skill directory" in d.reason

    def test_append_windows_sep_denied(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="shell", target="echo x >> skills\\pwn.txt", write=True))
        assert not d.allow

    def test_copy_move_delete_skills_denied(self) -> None:
        engine = PolicyEngine()
        for cmd in (
            "rm -rf skills/keep",
            r"del /q skills\keep\SKILL.md",
            "cp a.txt skills/pwn.txt",
            r"move x skills\pwn.txt",
        ):
            d = engine.decide(Action(dimension="shell", target=cmd, write=True))
            assert not d.allow, cmd

    def test_readonly_skills_still_confirm(self) -> None:
        """Read-only skills commands are not blocked; they keep the original L2 tier."""
        engine = PolicyEngine()
        for cmd in ("dir skills", r"type skills\keep\SKILL.md", "grep x skills/README.md"):
            d = engine.decide(Action(dimension="shell", target=cmd, write=True))
            assert d.allow and d.level == Level.L2_CONFIRM, cmd

    def test_write_outside_skills_still_confirm(self) -> None:
        engine = PolicyEngine()
        d = engine.decide(Action(dimension="shell", target="echo ok > repo/a.txt", write=True))
        assert d.allow and d.level == Level.L2_CONFIRM


class TestShellReadRootsGuard:
    """run_shell commands clearly writing/deleting an extra read-only root subtree are refused outright, ahead of L2;
    paths inside write_roots are not blocked (still L2, consistent with the fs dimension); skills-guard semantics unchanged."""

    @staticmethod
    def _engine(tmp_path, *, read_roots=(), write_roots=()) -> PolicyEngine:
        return PolicyEngine(
            fs=FsPolicy(
                roots=(str(tmp_path / "ws"),),
                read_roots=tuple(read_roots),
                write_roots=tuple(write_roots),
            )
        )

    def test_redirect_into_read_root_denied(self, tmp_path) -> None:
        root = tmp_path / "docs"
        engine = self._engine(tmp_path, read_roots=(str(root),))
        d = engine.decide(
            Action(dimension="shell", target=f"echo x > {root / 'a.txt'}", write=True)
        )
        assert not d.allow
        assert "read-only additional roots" in d.reason

    def test_copy_move_delete_read_root_denied(self, tmp_path) -> None:
        root = tmp_path / "docs"
        engine = self._engine(tmp_path, read_roots=(str(root),))
        for cmd in (
            f"rm -rf {root / 'keep'}",
            f"del /q {root / 'a.txt'}",
            f"cp a.txt {root / 'pwn.txt'}",
            f"move x {root / 'pwn.txt'}",
        ):
            d = engine.decide(Action(dimension="shell", target=cmd, write=True))
            assert not d.allow, cmd

    def test_under_write_root_still_confirm(self, tmp_path) -> None:
        """read_root parent + write_root child: writes in the subtree are not blocked (still L2); the rest of the parent stays refused."""
        read_root = tmp_path / "proj"
        write_root = read_root / "out"
        engine = self._engine(
            tmp_path, read_roots=(str(read_root),), write_roots=(str(write_root),)
        )
        d = engine.decide(
            Action(dimension="shell", target=f"echo x > {write_root / 'a.txt'}", write=True)
        )
        assert d.allow and d.level == Level.L2_CONFIRM
        d = engine.decide(
            Action(dimension="shell", target=f"echo x > {read_root / 'b.txt'}", write=True)
        )
        assert not d.allow

    def test_readonly_commands_still_confirm(self, tmp_path) -> None:
        """Read-only commands (type/cat) are not blocked; they keep the original L2 tier."""
        root = tmp_path / "docs"
        engine = self._engine(tmp_path, read_roots=(str(root),))
        for cmd in (f"type {root}\\keep.txt", f"cat {root}/a.txt"):
            d = engine.decide(Action(dimension="shell", target=cmd, write=True))
            assert d.allow and d.level == Level.L2_CONFIRM, cmd

    def test_workspace_relative_write_still_confirm(self, tmp_path) -> None:
        """Writes inside the workspace (cwd pinned to the workspace) are unaffected by the extra-root guards — regression check."""
        engine = self._engine(tmp_path, read_roots=(str(tmp_path / "docs"),))
        d = engine.decide(Action(dimension="shell", target="echo ok > a.txt", write=True))
        assert d.allow and d.level == Level.L2_CONFIRM

    def test_read_roots_hot_from_settings(self, tmp_path) -> None:
        """Extra roots read hot (same source as the fs decision): live settings values apply without a restart."""
        root = tmp_path / "docs"
        settings = _FakeSettings({"agent.fs.read_roots": [str(root)]})
        engine = PolicyEngine(fs=FsPolicy(roots=(str(tmp_path / "ws"),)), settings=settings)
        d = engine.decide(
            Action(dimension="shell", target=f"echo x > {root / 'a.txt'}", write=True)
        )
        assert not d.allow


class _FakeSettings:
    """Minimal settings handle (only get is needed); values mock the settings store."""

    def __init__(self, values: dict) -> None:
        self._values = values

    def get(self, key: str):
        return self._values.get(key)


class TestHotNetworkSettings:
    """Network decisions read settings hot: without settings the construction snapshot is used; with settings, live reads each time."""

    def test_settings_override_construction_snapshot(self) -> None:
        settings = _FakeSettings(
            {"agent.network.mode": "all", "agent.network.domains": ["github.com"]}
        )
        engine = PolicyEngine(network=NetworkPolicy(mode="off"), settings=settings)
        d = engine.decide(Action(dimension="network", target="https://example.com"))
        assert (
            d.allow and d.level == Level.L1_NOTIFY
        )  # built as off, but the decision follows settings

    def test_whitelist_domains_read_from_settings(self) -> None:
        settings = _FakeSettings(
            {"agent.network.mode": "whitelist", "agent.network.domains": ["pypi.org"]}
        )
        engine = PolicyEngine(network=NetworkPolicy(mode="all"), settings=settings)
        assert engine.decide(Action(dimension="network", target="https://pypi.org/x")).allow
        assert not engine.decide(Action(dimension="network", target="https://github.com/x")).allow

    def test_no_settings_keeps_construction_snapshot(self) -> None:
        engine = PolicyEngine(network=NetworkPolicy(mode="off"))
        assert not engine.decide(Action(dimension="network", target="https://github.com/x")).allow

    def test_narrow_network_takes_stricter(self) -> None:
        assert (
            narrow_network("whitelist", "all") == "whitelist"
        )  # a custom all-open is clamped back to global
        assert narrow_network("whitelist", "off") == "off"  # a stricter custom value takes effect
        assert narrow_network("off", "all") == "off"
        assert narrow_network("all", "all") == "all"
        assert narrow_network("whitelist", "whitelist") == "whitelist"


class TestHotAppSettings:
    """Hot reads for the in-app capability allowlist: without settings the construction snapshot is used; with settings, live reads."""

    def test_settings_override_allowed(self) -> None:
        settings = _FakeSettings(
            {"agent.app.allowed": ["notes__create_note"], "agent.app.denied": []}
        )
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset({"*"})), settings=settings)
        assert engine.decide(Action(dimension="app", target="notes__create_note")).allow
        assert not engine.decide(Action(dimension="app", target="graph__search")).allow

    def test_settings_denied_beats_wildcard(self) -> None:
        settings = _FakeSettings(
            {"agent.app.allowed": ["*"], "agent.app.denied": ["notes__delete_note"]}
        )
        engine = PolicyEngine(app=AppPolicy(), settings=settings)
        assert not engine.decide(Action(dimension="app", target="notes__delete_note")).allow
        assert engine.decide(Action(dimension="app", target="graph__search")).allow

    def test_settings_prefix_denied(self) -> None:
        settings = _FakeSettings({"agent.app.allowed": ["*"], "agent.app.denied": ["notes__*"]})
        engine = PolicyEngine(app=AppPolicy(), settings=settings)
        assert not engine.decide(Action(dimension="app", target="notes__create_note")).allow
        assert engine.decide(Action(dimension="app", target="graph__search")).allow

    def test_invalid_settings_falls_back_to_snapshot(self) -> None:
        settings = _FakeSettings(
            {"agent.app.allowed": "not-a-list", "agent.app.denied": ["notes__delete_note"]}
        )
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset({"*"})), settings=settings)
        assert engine.decide(Action(dimension="app", target="notes__create_note")).allow

    def test_no_settings_keeps_construction_snapshot(self) -> None:
        engine = PolicyEngine(app=AppPolicy(allowed=frozenset({"*"})))
        assert engine.decide(Action(dimension="app", target="notes__create_note")).allow
