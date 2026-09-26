"""Tests for the fs tool surface and its policy: the workspace jail, extra
read/write roots (static and hot-read), and atomic write behavior."""

import os

from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import Toolbelt, fs_tools


def _belt(root, *, confirm=None, notify=None) -> Toolbelt:
    return Toolbelt(
        fs_tools([root]),
        PolicyEngine(fs=FsPolicy(roots=(str(root),))),
        confirm=confirm,
        notify=notify,
    )


async def _yes() -> bool:
    return True


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


class _FakeSettings:
    def __init__(self, values: dict) -> None:
        self._values = values

    def get(self, key: str):
        return self._values.get(key)
