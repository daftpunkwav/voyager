"""Tests for the toolbelt and workspace: fs jail, capability trimming, and the
L1/L2 confirm channels.
"""

import sys
from pathlib import Path

import pytest
from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import Toolbelt, ensure_workdir, fs_tools
from agent.tools.workspace import shell_tools


@pytest.fixture()
def workdir(tmp_path):
    root = ensure_workdir(tmp_path / "workspace")
    return root


def _belt(root, *, confirm=None, notify=None) -> Toolbelt:
    return Toolbelt(
        fs_tools([root]),
        PolicyEngine(fs=FsPolicy(roots=(str(root),))),
        confirm=confirm,
        notify=notify,
    )


class TestFsJail:
    async def test_write_read_list_delete(self, workdir) -> None:
        belt = _belt(workdir, confirm=lambda _p: _yes())
        assert "repo/" in await belt.call(ToolCall("1", "list_dir", {"path": "."}))
        await belt.call(ToolCall("2", "write_file", {"path": "repo/a.md", "content": "你好"}))
        assert "你好" in await belt.call(ToolCall("3", "read_file", {"path": "repo/a.md"}))
        out = await belt.call(ToolCall("4", "delete_file", {"path": "repo/a.md"}))
        assert "deleted" in out

    async def test_outside_jail_rejected_twice(self, workdir, tmp_path) -> None:
        """Two layers of protection: the inner jail plus the outer policy."""
        belt = _belt(workdir)
        out = await belt.call(
            ToolCall("1", "write_file", {"path": str(tmp_path / "evil.txt"), "content": "x"})
        )
        assert "[已拒绝]" in out
        assert not (tmp_path / "evil.txt").exists()

    def test_ensure_workdir_categories(self, workdir) -> None:
        for cat in ("repo", "books", "news", "exports", "imports", "sandbox"):
            assert (workdir / cat).is_dir()

    async def test_skills_write_denied(self, workdir) -> None:
        """skills/ is write-protected: refused at the policy layer, nothing lands on disk."""
        belt = _belt(workdir)
        out = await belt.call(
            ToolCall("1", "write_file", {"path": "skills/pwn/SKILL.md", "content": "pwn"})
        )
        assert "[已拒绝]" in out
        assert not (workdir / "skills").exists()  # not even the parent directory may be created

    async def test_skills_write_via_dotdot_denied(self, workdir) -> None:
        """repo/../skills still resolves under skills and is refused the same way."""
        belt = _belt(workdir)
        out = await belt.call(
            ToolCall("1", "write_file", {"path": "repo/../skills/pwn/SKILL.md", "content": "pwn"})
        )
        assert "[已拒绝]" in out
        assert not (workdir / "skills" / "pwn").exists()

    async def test_skills_delete_denied_without_confirm(self, workdir) -> None:
        """Deleting into skills is refused outright, never raising the L2 confirmation; the file survives."""
        asked: list[str] = []

        async def spy_confirm(prompt: str) -> bool:
            asked.append(prompt)
            return True

        keep = workdir / "skills" / "keep" / "SKILL.md"
        keep.parent.mkdir(parents=True)
        keep.write_text("# keep\n", encoding="utf-8")
        belt = _belt(workdir, confirm=spy_confirm)
        out = await belt.call(ToolCall("1", "delete_file", {"path": "skills/keep/SKILL.md"}))
        assert "[已拒绝]" in out
        assert keep.exists()
        assert (
            asked == []
        )  # refusal happens before confirmation; the confirm channel is never asked

    async def test_skills_read_list_still_ok(self, workdir) -> None:
        keep = workdir / "skills" / "keep" / "SKILL.md"
        keep.parent.mkdir(parents=True)
        keep.write_text("# keep\n", encoding="utf-8")
        belt = _belt(workdir)
        text = await belt.call(ToolCall("1", "read_file", {"path": "skills/keep/SKILL.md"}))
        assert "# keep" in text
        listing = await belt.call(ToolCall("2", "list_dir", {"path": "skills"}))
        assert "keep/" in listing

    async def test_repo_write_regression(self, workdir) -> None:
        """Non-skills categories remain writable (regression check)."""
        belt = _belt(workdir)
        out = await belt.call(ToolCall("1", "write_file", {"path": "repo/a.md", "content": "x"}))
        assert "written" in out

    async def test_list_missing_or_file_reports(self, workdir) -> None:
        belt = _belt(workdir)
        out = await belt.call(ToolCall("1", "list_dir", {"path": "repo/nope"}))
        assert out.startswith("[失败]")
        (workdir / "repo" / "f.txt").write_text("x", encoding="utf-8")
        out = await belt.call(ToolCall("2", "list_dir", {"path": "repo/f.txt"}))
        assert out.startswith("[参数错误]")

    async def test_delete_missing_or_directory_reports(self, workdir) -> None:
        belt = _belt(workdir, confirm=lambda _p: _yes())
        out = await belt.call(ToolCall("1", "delete_file", {"path": "repo/nope"}))
        assert out.startswith("[失败]")
        out = await belt.call(ToolCall("2", "delete_file", {"path": "repo"}))
        assert out.startswith("[参数错误]")


async def _yes() -> bool:
    return True


class TestTrim:
    def test_trimmed_removes_write(self, workdir) -> None:
        """Trimming away write means it is truly gone."""
        belt = _belt(workdir).trimmed(["read_file"])
        assert belt.names() == ["read_file"]
        assert belt._policy is not None  # trimming keeps the policy engine

    async def test_trimmed_call_blocked(self, workdir) -> None:
        belt = _belt(workdir).trimmed(["read_file"])
        out = await belt.call(ToolCall("1", "write_file", {"path": "a", "content": "b"}))
        assert "[未知工具]" in out

    async def test_unknown_tool_suggests_closest_names(self, workdir) -> None:
        """A typo'd or ungranted name gets the roster's nearest matches, so
        the model can self-correct in one call."""
        belt = _belt(workdir)
        out = await belt.call(ToolCall("1", "read_fiel", {"path": "a"}))
        assert "[未知工具]" in out
        assert "read_file" in out
        # a name with no roster neighbour gets no hint segment
        out = await belt.call(ToolCall("1", "zzzQQQ", {}))
        assert "[未知工具]" in out
        assert "最接近的工具" not in out

    def test_trimmed_prefix_expand_relative_to_belt(self, workdir) -> None:
        """Prefix grants expand against the current roster; new prefix names outside the allowlist never enter."""
        belt = _belt(workdir)
        trimmed = belt.trimmed(["read_*", "list_dir"])
        assert set(trimmed.names()) == {"read_file", "list_dir"}
        # No notes__* domain in the roster: prefixes never invent tools
        assert not any(n.startswith("notes__") for n in trimmed.names())

    def test_trimmed_bare_star_is_not_prefix(self, workdir) -> None:
        """A bare `*` is not a valid prefix grant (avoiding opening the whole roster in one stroke)."""
        belt = _belt(workdir).trimmed(["*"])
        assert belt.names() == []


class TestConfirmFlow:
    async def test_l2_confirm_approve_and_deny(self, workdir) -> None:
        asked: list[str] = []
        (workdir / "f.txt").touch()

        async def nope(_prompt: str) -> bool:
            asked.append(_prompt)
            return False

        belt = _belt(workdir, confirm=nope)
        out = await belt.call(ToolCall("1", "delete_file", {"path": "f.txt"}))
        assert "[已取消]" in out and asked  # the confirm prompt really fired
        assert (workdir / "f.txt").exists()  # not deleted

    async def test_l2_without_channel_skipped(self, workdir) -> None:
        (workdir / "f.txt").touch()
        belt = _belt(workdir)  # no confirm channel
        out = await belt.call(ToolCall("1", "delete_file", {"path": "f.txt"}))
        assert "[需确认]" in out
        assert (workdir / "f.txt").exists()

    async def test_l1_notify_fired(self, workdir) -> None:
        seen: list[str] = []
        (workdir / "f.txt").write_text("x")

        async def notify(msg: str) -> None:
            seen.append(msg)

        belt = _belt(workdir, notify=notify)
        await belt.call(ToolCall("1", "write_file", {"path": "g.txt", "content": "y"}))
        assert seen and "write_file" in seen[0]

    async def test_unknown_tool(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "nope", {}))
        assert "[未知工具]" in out


class TestAppPolicyTarget:
    async def test_app_dimension_uses_tool_name_not_url(self) -> None:
        """The app dimension uses the tool name as target; bridge tools carrying a url argument still match by tool name."""
        from agent.llm import ToolCall
        from agent.policy import AppPolicy, PolicyEngine
        from agent.tools import AgentTool, Toolbelt

        async def handler(url: str = "") -> dict:
            return {"ok": True, "url": url}

        tool = AgentTool(
            name="notes__create_note",
            description="写笔记",
            handler=handler,
            schema={"url": {"type": "string"}},
            dimension="app",
            write=True,
        )
        allowed = Toolbelt(
            {"notes__create_note": tool},
            PolicyEngine(app=AppPolicy(allowed=frozenset({"notes__create_note"}))),
        )
        out = await allowed.call(ToolCall("1", "notes__create_note", {"url": "https://evil.com"}))
        assert "ok" in out

        denied = Toolbelt(
            {"notes__create_note": tool},
            PolicyEngine(
                app=AppPolicy(allowed=frozenset({"*"}), denied=frozenset({"notes__create_note"}))
            ),
        )
        out = await denied.call(ToolCall("2", "notes__create_note", {"url": "https://github.com"}))
        assert "[已拒绝]" in out


class TestShellGuard:
    async def test_destructive_commands_blocked(self, tmp_path) -> None:
        """Machine-wrecking commands are hard-blocked before execution (even without an L2 confirm channel)."""
        run_shell = shell_tools(tmp_path)["run_shell"].handler
        for cmd in (
            "mkfs.ext4 /dev/sda1",
            "dd if=a of=/dev/sda",
            "shutdown now",
            "rm -rf /",
            "rm -rf ~",
            "format C: /q",
        ):
            out = await run_shell(cmd, timeout=2)
            assert "[已拒绝]" in out, cmd

    async def test_normal_command_not_blocked(self, tmp_path) -> None:
        run_shell = shell_tools(tmp_path)["run_shell"].handler
        # Not via the shell: interpreter -c avoids Windows' builtin echo; no nested quotes so shlex does not mis-split in nt mode
        out = await run_shell(f"{sys.executable} -c print(42)", timeout=5)
        assert "已拒绝" not in out and "42" in out

    async def test_large_output_not_tool_truncated(self, tmp_path) -> None:
        """Output beyond the old 10k tool-local cap comes back whole; the
        invoke-layer result budget (spill) decides what the model sees."""
        # a script file instead of -c quoting: nt-mode shlex keeps literal
        # quotes, which turn a -c program into a bare string expression
        script = tmp_path / "_big.py"
        script.write_text("print('x' * 50000)", encoding="utf-8")
        run_shell = shell_tools(tmp_path)["run_shell"].handler
        out = await run_shell(f"{sys.executable} {script.name}", timeout=15)
        assert out.startswith("exit=0\n")
        assert "x" * 50000 in out
        assert "截断" not in out

    async def test_timeout_reports_captured_output(self, tmp_path) -> None:
        script = tmp_path / "_slow.py"
        script.write_text(
            "import time\nprint('early', flush=True)\ntime.sleep(30)\n", encoding="utf-8"
        )
        run_shell = shell_tools(tmp_path)["run_shell"].handler
        out = await run_shell(f"{sys.executable} {script.name}", timeout=1.5)
        assert out.startswith("[超时]")
        assert "early" in out

    async def test_missing_executable_does_not_fall_back_to_shell(self, tmp_path) -> None:
        run_shell = shell_tools(tmp_path)["run_shell"].handler
        # Not echo: /bin/echo really exists on Unix, which would mask the no-shell-fallback behavior
        out = await run_shell("__no_such_cmd_xyz__", timeout=5)
        assert "[失败]" in out and "找不到可执行文件" in out

    async def test_subprocess_cwd_pinned_to_workspace(self, tmp_path) -> None:
        """The subprocess cwd is pinned to the assembly directory: relative-path scripts are found,
        and relatively written files land there rather than in the process cwd or parent."""
        work = tmp_path / "ws"
        work.mkdir()
        probe = work / "_cwd_probe.py"
        probe.write_text(
            "from pathlib import Path\n"
            "Path('cwd-probe-phase35.txt').write_text('ok', encoding='utf-8')\n",
            encoding="utf-8",
        )
        run_shell = shell_tools(work)["run_shell"].handler
        stray = Path.cwd() / "cwd-probe-phase35.txt"
        try:
            out = await run_shell(f"{sys.executable} {probe.name}", timeout=5)
            assert "exit=0" in out, out
            assert (work / "cwd-probe-phase35.txt").read_text(encoding="utf-8") == "ok"
            assert not (tmp_path / "cwd-probe-phase35.txt").exists()  # nothing lands in the parent
            # If the implementation drops cwd=, the file lands in the process cwd and this fails
            if Path.cwd().resolve() != work.resolve():
                assert not stray.exists()
        finally:
            # Guard against a cwd=-less implementation dirtying the repo root: clean up any leftover file in the process cwd
            if stray.exists():
                stray.unlink()

    async def test_shell_skills_write_denied_by_policy(self, workdir) -> None:
        """The policy layer refuses shell writes into skills ahead of L2; nothing lands on disk."""
        belt = Toolbelt(
            {**fs_tools([workdir]), **shell_tools(workdir)},
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(ToolCall("1", "run_shell", {"command": "echo pwn > skills/x.txt"}))
        assert "[已拒绝]" in out
        assert not (workdir / "skills" / "x.txt").exists()

    async def test_shell_readonly_skills_still_needs_confirm(self, workdir) -> None:
        """Read-only skills commands are not caught by the new gate: with no confirm channel they still yield needs-confirm (L2 unchanged)."""
        belt = Toolbelt(
            {**fs_tools([workdir]), **shell_tools(workdir)},
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(
            ToolCall("1", "run_shell", {"command": "type skills\\keep\\SKILL.md"})
        )
        assert "[需确认]" in out


class TestFsReadRoots:
    """Extra read-only roots end to end: policy and tool layers agree — read tools admit extra
    roots while writes/deletes are refused at both layers."""

    def _belt_with_read_root(self, workdir, docs) -> Toolbelt:
        return Toolbelt(
            fs_tools([workdir], read_roots=[docs]),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),), read_roots=(str(docs),))),
        )

    async def test_read_file_in_read_root_allowed(self, workdir, tmp_path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "a.txt").write_text("附加根内容", encoding="utf-8")
        belt = self._belt_with_read_root(workdir, docs)
        out = await belt.call(ToolCall("1", "read_file", {"path": str(docs / "a.txt")}))
        assert "附加根内容" in out

    async def test_list_dir_in_read_root_allowed(self, workdir, tmp_path) -> None:
        docs = tmp_path / "docs"
        (docs / "sub").mkdir(parents=True)
        belt = self._belt_with_read_root(workdir, docs)
        out = await belt.call(ToolCall("1", "list_dir", {"path": str(docs)}))
        assert "sub/" in out

    async def test_write_in_read_root_denied(self, workdir, tmp_path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        belt = self._belt_with_read_root(workdir, docs)
        out = await belt.call(
            ToolCall("1", "write_file", {"path": str(docs / "pwn.txt"), "content": "x"})
        )
        assert "[已拒绝]" in out
        assert not (docs / "pwn.txt").exists()

    async def test_delete_in_read_root_denied_without_confirm(self, workdir, tmp_path) -> None:
        """Deletes in extra roots are refused outright, never raising the L2 confirmation; the file survives."""
        docs = tmp_path / "docs"
        docs.mkdir()
        target = docs / "keep.txt"
        target.write_text("keep", encoding="utf-8")
        belt = self._belt_with_read_root(workdir, docs)
        out = await belt.call(ToolCall("1", "delete_file", {"path": str(target)}))
        assert "[已拒绝]" in out
        assert target.exists()

    async def test_read_outside_all_roots_still_denied(self, workdir, tmp_path) -> None:
        """Without extra roots (or for paths outside all roots), reads are refused at both layers — the original behavior."""
        belt = Toolbelt(
            fs_tools([workdir]),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(ToolCall("1", "read_file", {"path": str(tmp_path / "evil.txt")}))
        assert "[已拒绝]" in out

    async def test_hot_read_roots_fn_without_rebuild(self, workdir, tmp_path) -> None:
        """read_roots_fn reads hot: after a settings change, policy and tool layers admit in lockstep with no Toolbelt rebuild."""
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "a.txt").write_text("热读内容", encoding="utf-8")
        values: dict[str, list[str]] = {"agent.fs.read_roots": []}
        settings = _FakeSettings(values)
        belt = Toolbelt(
            fs_tools(
                [workdir],
                read_roots=[],
                read_roots_fn=lambda: list(settings.get("agent.fs.read_roots") or ()),
            ),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),)), settings=settings),
        )
        denied = await belt.call(ToolCall("1", "read_file", {"path": str(docs / "a.txt")}))
        assert "[已拒绝]" in denied
        values["agent.fs.read_roots"] = [str(docs)]
        allowed = await belt.call(ToolCall("2", "read_file", {"path": str(docs / "a.txt")}))
        assert "热读内容" in allowed


class TestFsWriteRoots:
    """Extra read-write roots end to end: policy and tool layers agree — reads are admitted,
    writes/deletes go through L2 confirmation, and read_root-only paths still refuse writes at both layers."""

    def _belt(self, workdir, *, write_roots=(), read_roots=(), confirm=None) -> Toolbelt:
        return Toolbelt(
            fs_tools([workdir], read_roots=list(read_roots), write_roots=list(write_roots)),
            PolicyEngine(
                fs=FsPolicy(
                    roots=(str(workdir),),
                    read_roots=tuple(read_roots),
                    write_roots=tuple(write_roots),
                )
            ),
            confirm=confirm,
        )

    async def test_read_and_list_in_write_root_allowed(self, workdir, tmp_path) -> None:
        proj = tmp_path / "proj"
        (proj / "sub").mkdir(parents=True)
        (proj / "a.txt").write_text("读写根内容", encoding="utf-8")
        (proj / "sub" / "b.txt").write_text("x", encoding="utf-8")
        belt = self._belt(workdir, write_roots=[proj])
        text = await belt.call(ToolCall("1", "read_file", {"path": str(proj / "a.txt")}))
        assert "读写根内容" in text
        listing = await belt.call(ToolCall("2", "list_dir", {"path": str(proj / "sub")}))
        assert "b.txt" in listing

    async def test_write_without_confirm_channel_not_landed(self, workdir, tmp_path) -> None:
        """Writes inside write_roots go through L2: with no confirm channel they are skipped and never land."""
        proj = tmp_path / "proj"
        proj.mkdir()
        belt = self._belt(workdir, write_roots=[proj])
        out = await belt.call(
            ToolCall("1", "write_file", {"path": str(proj / "a.txt"), "content": "x"})
        )
        assert "[需确认]" in out
        assert not (proj / "a.txt").exists()

    async def test_write_with_confirm_lands(self, workdir, tmp_path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        belt = self._belt(workdir, write_roots=[proj], confirm=lambda _p: _yes())
        out = await belt.call(
            ToolCall("1", "write_file", {"path": str(proj / "sub" / "a.txt"), "content": "x"})
        )
        assert "written" in out
        assert (proj / "sub" / "a.txt").read_text(encoding="utf-8") == "x"

    async def test_delete_without_confirm_not_removed(self, workdir, tmp_path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        target = proj / "keep.txt"
        target.write_text("keep", encoding="utf-8")
        belt = self._belt(workdir, write_roots=[proj])
        out = await belt.call(ToolCall("1", "delete_file", {"path": str(target)}))
        assert "[需确认]" in out
        assert target.exists()

    async def test_delete_with_confirm_removes(self, workdir, tmp_path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        target = proj / "gone.txt"
        target.write_text("x", encoding="utf-8")
        belt = self._belt(workdir, write_roots=[proj], confirm=lambda _p: _yes())
        out = await belt.call(ToolCall("1", "delete_file", {"path": str(target)}))
        assert "deleted" in out
        assert not target.exists()

    async def test_write_in_read_root_only_denied(self, workdir, tmp_path) -> None:
        """Writes to read_root-only paths stay refused: write_roots never relaxes read-only roots."""
        docs = tmp_path / "docs"
        docs.mkdir()
        belt = self._belt(
            workdir, read_roots=[docs], write_roots=[tmp_path / "proj"], confirm=lambda _p: _yes()
        )
        out = await belt.call(
            ToolCall("1", "write_file", {"path": str(docs / "pwn.txt"), "content": "x"})
        )
        assert "[已拒绝]" in out
        assert not (docs / "pwn.txt").exists()

    async def test_hot_write_roots_fn_without_rebuild(self, workdir, tmp_path) -> None:
        """write_roots_fn reads hot: after a settings change, policy and tool layers admit in lockstep with no
        Toolbelt rebuild; once admitted, writes still go through L2 confirmation (no channel -> needs-confirm)."""
        proj = tmp_path / "proj"
        proj.mkdir()
        values: dict[str, list[str]] = {"agent.fs.write_roots": []}
        settings = _FakeSettings(values)
        belt = Toolbelt(
            fs_tools(
                [workdir],
                write_roots=[],
                write_roots_fn=lambda: list(settings.get("agent.fs.write_roots") or ()),
            ),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),)), settings=settings),
        )
        denied = await belt.call(
            ToolCall("1", "write_file", {"path": str(proj / "a.txt"), "content": "x"})
        )
        assert "[已拒绝]" in denied
        values["agent.fs.write_roots"] = [str(proj)]
        confirmed = await belt.call(
            ToolCall("2", "write_file", {"path": str(proj / "a.txt"), "content": "x"})
        )
        assert "[需确认]" in confirmed


class _FakeSettings:
    def __init__(self, values: dict) -> None:
        self._values = values

    def get(self, key: str):
        return self._values.get(key)
