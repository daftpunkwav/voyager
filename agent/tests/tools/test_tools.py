"""Tests for the toolbelt and workspace: fs jail, capability trimming, and the
L1/L2 confirm channels.
"""

import os
import re
import sys
from pathlib import Path

import pytest
from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import Toolbelt, ensure_workdir, fs_tools
from agent.tools.workspace import shell_tools
from agent.tools.workspace.console_decode import decode_console_output


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
    async def test_write_and_read(self, workdir) -> None:
        belt = _belt(workdir, confirm=lambda _p: _yes())
        await belt.call(ToolCall("2", "write", {"path": "repo/a.md", "content": "你好"}))
        assert "你好" in await belt.call(ToolCall("3", "read", {"path": "repo/a.md"}))

    async def test_outside_jail_rejected_twice(self, workdir, tmp_path) -> None:
        """Two layers of protection: the inner jail plus the outer policy."""
        belt = _belt(workdir)
        out = await belt.call(
            ToolCall("1", "write", {"path": str(tmp_path / "evil.txt"), "content": "x"})
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
            ToolCall("1", "write", {"path": "skills/pwn/SKILL.md", "content": "pwn"})
        )
        assert "[已拒绝]" in out
        assert not (workdir / "skills").exists()  # not even the parent directory may be created

    async def test_skills_write_via_dotdot_denied(self, workdir) -> None:
        """repo/../skills still resolves under skills and is refused the same way."""
        belt = _belt(workdir)
        out = await belt.call(
            ToolCall("1", "write", {"path": "repo/../skills/pwn/SKILL.md", "content": "pwn"})
        )
        assert "[已拒绝]" in out
        assert not (workdir / "skills" / "pwn").exists()

    async def test_skills_read_still_ok(self, workdir) -> None:
        keep = workdir / "skills" / "keep" / "SKILL.md"
        keep.parent.mkdir(parents=True)
        keep.write_text("# keep\n", encoding="utf-8")
        belt = _belt(workdir)
        text = await belt.call(ToolCall("1", "read", {"path": "skills/keep/SKILL.md"}))
        assert "# keep" in text

    async def test_repo_write_regression(self, workdir) -> None:
        """Non-skills categories remain writable (regression check)."""
        belt = _belt(workdir)
        out = await belt.call(ToolCall("1", "write", {"path": "repo/a.md", "content": "x"}))
        assert "written" in out


async def _yes() -> bool:
    return True


class TestTrim:
    def test_trimmed_removes_write(self, workdir) -> None:
        """Trimming away write means it is truly gone."""
        belt = _belt(workdir).trimmed(["read"])
        assert belt.names() == ["read"]
        assert belt._policy is not None  # trimming keeps the policy engine

    async def test_trimmed_call_blocked(self, workdir) -> None:
        belt = _belt(workdir).trimmed(["read"])
        out = await belt.call(ToolCall("1", "write", {"path": "a", "content": "b"}))
        assert "[未知工具]" in out

    async def test_unknown_tool_suggests_closest_names(self, workdir) -> None:
        """A typo'd or ungranted name gets the roster's nearest matches, so
        the model can self-correct in one call."""
        belt = _belt(workdir)
        out = await belt.call(ToolCall("1", "rea", {"path": "a"}))
        assert "[未知工具]" in out
        assert "read" in out
        # a name with no roster neighbour gets no hint segment
        out = await belt.call(ToolCall("1", "zzzQQQ", {}))
        assert "[未知工具]" in out
        assert "最接近的工具" not in out

    def test_trimmed_prefix_expand_relative_to_belt(self, workdir) -> None:
        """Grants expand against the current roster: explicit names pass, a
        prefix with no roster match invents nothing."""
        belt = _belt(workdir)
        trimmed = belt.trimmed(["read", "edit"])
        assert set(trimmed.names()) == {"read", "edit"}
        # No roster name starts with "note_": the prefix never invents tools
        assert belt.trimmed(["note_*"]).names() == []
        assert not any(n.startswith("notes__") for n in trimmed.names())

    def test_trimmed_bare_star_is_not_prefix(self, workdir) -> None:
        """A bare `*` is not a valid prefix grant (avoiding opening the whole roster in one stroke)."""
        belt = _belt(workdir).trimmed(["*"])
        assert belt.names() == []


class TestConfirmFlow:
    async def test_l2_confirm_approve_and_deny(self, workdir, tmp_path) -> None:
        asked: list[str] = []
        proj = tmp_path / "proj"
        proj.mkdir()

        async def nope(_prompt: str) -> bool:
            asked.append(_prompt)
            return False

        belt = Toolbelt(
            fs_tools([workdir], write_roots=[proj]),
            PolicyEngine(
                fs=FsPolicy(roots=(str(workdir),), write_roots=(str(proj),)),
            ),
            confirm=nope,
        )
        out = await belt.call(ToolCall("1", "write", {"path": str(proj / "f.txt"), "content": "x"}))
        assert "[已取消]" in out and asked  # the confirm prompt really fired
        assert not (proj / "f.txt").exists()  # nothing written

    async def test_l2_without_channel_skipped(self, workdir, tmp_path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        belt = Toolbelt(
            fs_tools([workdir], write_roots=[proj]),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),), write_roots=(str(proj),))),
        )  # no confirm channel
        out = await belt.call(ToolCall("1", "write", {"path": str(proj / "f.txt"), "content": "x"}))
        assert "[需确认]" in out
        assert not (proj / "f.txt").exists()

    async def test_l1_notify_fired(self, workdir) -> None:
        seen: list[str] = []
        (workdir / "f.txt").write_text("x")

        async def notify(msg: str) -> None:
            seen.append(msg)

        belt = _belt(workdir, notify=notify)
        await belt.call(ToolCall("1", "write", {"path": "g.txt", "content": "y"}))
        assert seen and "write" in seen[0]

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
        bash = shell_tools(tmp_path)["bash"].handler
        for cmd in (
            "mkfs.ext4 /dev/sda1",
            "dd if=a of=/dev/sda",
            "shutdown now",
            "rm -rf /",
            "rm -rf ~",
            "format C: /q",
        ):
            out = await bash(cmd, timeout=2)
            assert "[已拒绝]" in out, cmd

    async def test_normal_command_not_blocked(self, tmp_path) -> None:
        bash = shell_tools(tmp_path)["bash"].handler
        # Not via the shell: interpreter -c avoids Windows' builtin echo; no nested quotes so shlex does not mis-split in nt mode
        out = await bash(f"{sys.executable} -c print(42)", timeout=5)
        assert "已拒绝" not in out and "42" in out

    async def test_large_output_not_tool_truncated(self, tmp_path) -> None:
        """Output beyond the old 10k tool-local cap comes back whole; the
        invoke-layer result budget (spill) decides what the model sees."""
        # a script file instead of -c quoting: nt-mode shlex keeps literal
        # quotes, which turn a -c program into a bare string expression
        script = tmp_path / "_big.py"
        script.write_text("print('x' * 50000)", encoding="utf-8")
        bash = shell_tools(tmp_path)["bash"].handler
        out = await bash(f"{sys.executable} {script.name}", timeout=15)
        # codex-style structured header: exit code, wall time, captured lines
        assert re.match(r"exit=0 wall=\d+\.\d+s lines=\d+\n", out), out
        assert "x" * 50000 in out
        assert "截断" not in out

    async def test_timeout_reports_captured_output(self, tmp_path) -> None:
        script = tmp_path / "_slow.py"
        script.write_text(
            "import time\nprint('early', flush=True)\ntime.sleep(30)\n", encoding="utf-8"
        )
        bash = shell_tools(tmp_path)["bash"].handler
        out = await bash(f"{sys.executable} {script.name}", timeout=1.5)
        assert out.startswith("[超时]")
        assert "early" in out

    async def test_missing_executable_does_not_fall_back_to_shell(self, tmp_path) -> None:
        bash = shell_tools(tmp_path)["bash"].handler
        # Not echo: /bin/echo really exists on Unix, which would mask the no-shell-fallback behavior
        out = await bash("__no_such_cmd_xyz__", timeout=5)
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
        bash = shell_tools(work)["bash"].handler
        stray = Path.cwd() / "cwd-probe-phase35.txt"
        try:
            out = await bash(f"{sys.executable} {probe.name}", timeout=5)
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
        out = await belt.call(ToolCall("1", "bash", {"command": "echo pwn > skills/x.txt"}))
        assert "[已拒绝]" in out
        assert not (workdir / "skills" / "x.txt").exists()

    async def test_shell_readonly_skills_execute_without_confirm(self, workdir) -> None:
        """Confirm retired: read-only skills commands are not caught by the
        skills guard (a write there is still hard-rejected above) and reach
        execution without any confirm branch."""
        belt = Toolbelt(
            {**fs_tools([workdir]), **shell_tools(workdir)},
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(ToolCall("1", "bash", {"command": "type skills\\keep\\SKILL.md"}))
        assert "[需确认]" not in out and "[已取消]" not in out


class TestFsReadRoots:
    """Extra read-only roots end to end: policy and tool layers agree — read tools admit extra
    roots while writes are refused at both layers."""

    def _belt_with_read_root(self, workdir, docs) -> Toolbelt:
        return Toolbelt(
            fs_tools([workdir], read_roots=[docs]),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),), read_roots=(str(docs),))),
        )

    async def test_read_in_read_root_allowed(self, workdir, tmp_path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "a.txt").write_text("附加根内容", encoding="utf-8")
        belt = self._belt_with_read_root(workdir, docs)
        out = await belt.call(ToolCall("1", "read", {"path": str(docs / "a.txt")}))
        assert "附加根内容" in out

    async def test_write_in_read_root_denied(self, workdir, tmp_path) -> None:
        docs = tmp_path / "docs"
        docs.mkdir()
        belt = self._belt_with_read_root(workdir, docs)
        out = await belt.call(
            ToolCall("1", "write", {"path": str(docs / "pwn.txt"), "content": "x"})
        )
        assert "[已拒绝]" in out
        assert not (docs / "pwn.txt").exists()

    async def test_read_outside_all_roots_still_denied(self, workdir, tmp_path) -> None:
        """Without extra roots (or for paths outside all roots), reads are refused at both layers — the original behavior."""
        belt = Toolbelt(
            fs_tools([workdir]),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),))),
        )
        out = await belt.call(ToolCall("1", "read", {"path": str(tmp_path / "evil.txt")}))
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
        denied = await belt.call(ToolCall("1", "read", {"path": str(docs / "a.txt")}))
        assert "[已拒绝]" in denied
        values["agent.fs.read_roots"] = [str(docs)]
        allowed = await belt.call(ToolCall("2", "read", {"path": str(docs / "a.txt")}))
        assert "热读内容" in allowed


class TestFsWriteRoots:
    """Extra read-write roots end to end: policy and tool layers agree — reads are admitted,
    writes go through L2 confirmation, and read_root-only paths still refuse writes at both layers."""

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

    async def test_read_in_write_root_allowed(self, workdir, tmp_path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "a.txt").write_text("读写根内容", encoding="utf-8")
        belt = self._belt(workdir, write_roots=[proj])
        text = await belt.call(ToolCall("1", "read", {"path": str(proj / "a.txt")}))
        assert "读写根内容" in text

    async def test_write_without_confirm_channel_not_landed(self, workdir, tmp_path) -> None:
        """Writes inside write_roots go through L2: with no confirm channel they are skipped and never land."""
        proj = tmp_path / "proj"
        proj.mkdir()
        belt = self._belt(workdir, write_roots=[proj])
        out = await belt.call(ToolCall("1", "write", {"path": str(proj / "a.txt"), "content": "x"}))
        assert "[需确认]" in out
        assert not (proj / "a.txt").exists()

    async def test_write_with_confirm_lands(self, workdir, tmp_path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        belt = self._belt(workdir, write_roots=[proj], confirm=lambda _p: _yes())
        out = await belt.call(
            ToolCall("1", "write", {"path": str(proj / "sub" / "a.txt"), "content": "x"})
        )
        assert "written" in out
        assert (proj / "sub" / "a.txt").read_text(encoding="utf-8") == "x"

    async def test_write_in_read_root_only_denied(self, workdir, tmp_path) -> None:
        """Writes to read_root-only paths stay refused: write_roots never relaxes read-only roots."""
        docs = tmp_path / "docs"
        docs.mkdir()
        belt = self._belt(
            workdir, read_roots=[docs], write_roots=[tmp_path / "proj"], confirm=lambda _p: _yes()
        )
        out = await belt.call(
            ToolCall("1", "write", {"path": str(docs / "pwn.txt"), "content": "x"})
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
            ToolCall("1", "write", {"path": str(proj / "a.txt"), "content": "x"})
        )
        assert "[已拒绝]" in denied
        values["agent.fs.write_roots"] = [str(proj)]
        confirmed = await belt.call(
            ToolCall("2", "write", {"path": str(proj / "a.txt"), "content": "x"})
        )
        assert "[需确认]" in confirmed


class _FakeSettings:
    def __init__(self, values: dict) -> None:
        self._values = values

    def get(self, key: str):
        return self._values.get(key)


class TestShellCancellation:
    async def test_cancelled_bash_raises_and_returns_promptly(self, tmp_path) -> None:
        """Cancelling a running bash propagates CancelledError through the
        kill path (child killed, reader reaped) instead of leaking."""
        import asyncio

        script = tmp_path / "_hang.py"
        script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        bash = shell_tools(tmp_path)["bash"].handler
        task = asyncio.create_task(bash(f"{sys.executable} {script.name}", timeout=30))
        await asyncio.sleep(0.3)  # let the child start
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2)
            raised = False
        except asyncio.CancelledError:
            raised = True
        assert raised  # propagation preserved; child killed inside the handler


class TestWriteAtomic:
    async def test_failed_replace_keeps_original_and_cleans_tmp(self, workdir, monkeypatch) -> None:
        """A mid-write failure must not truncate the target nor leave a stray
        temp file."""
        target = workdir / "repo" / "a.txt"
        target.write_text("original", encoding="utf-8")

        real_replace = os.replace

        def _boom(src, dst):
            raise OSError("disk full (simulated)")

        monkeypatch.setattr(os, "replace", _boom)
        belt = _belt(workdir)
        out = await belt.call(ToolCall("1", "write", {"path": "repo/a.txt", "content": "new"}))
        monkeypatch.setattr(os, "replace", real_replace)
        assert "[工具失败]" in out
        assert target.read_text(encoding="utf-8") == "original"  # untouched
        assert not list((workdir / "repo").glob(".a.txt.*.tmp"))  # no stray tmp


class TestConsoleDecode:
    def test_utf8_still_wins(self) -> None:
        assert decode_console_output("中文 ok\n".encode()) == "中文 ok\n"

    def test_utf16_tried_when_nul_bytes_present(self, monkeypatch) -> None:
        """UTF-16LE output (some PowerShell pipelines) must decode as UTF-16:
        GBK accepts the NUL-interleaved bytes and would return mojibake, so
        the NUL heuristic has to put UTF-16 first in the fallback chain."""
        monkeypatch.setattr(os, "name", "nt")
        raw = "exit=0\n中文输出\n".encode("utf-16-le")
        assert decode_console_output(raw) == "exit=0\n中文输出\n"

    def test_gbk_fallback_without_nul_bytes(self, monkeypatch) -> None:
        assert decode_console_output("中文 ok\n".encode("gbk")) == "中文 ok\n"

    def test_undecodable_degrades_to_replacement(self, monkeypatch) -> None:
        assert "\ufffd" in decode_console_output(b"\xff\xfe\x81\x81\x81")
