"""Tests for atomic file editing (edit_file) and windowed reading
(read_file offset/limit): uniqueness guard, caps, error paths, and
byte-identical legacy whole reads.
"""

import json

import pytest
from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import Toolbelt, ensure_workdir, fs_tools


@pytest.fixture()
def workdir(tmp_path):
    root = ensure_workdir(tmp_path / "workspace")
    (root / "repo").mkdir(exist_ok=True)
    return root


def _belt(root, **kw) -> Toolbelt:
    return Toolbelt(
        fs_tools([root]),
        PolicyEngine(fs=FsPolicy(roots=(str(root),))),
        **kw,
    )


async def _yes() -> bool:
    return True


class TestReadWindow:
    async def test_default_read_is_legacy_identical(self, workdir) -> None:
        body = "one\ntwo\nthree\n"
        (workdir / "repo" / "a.txt").write_text(body, encoding="utf-8")
        out = await _belt(workdir).call(ToolCall("1", "read_file", {"path": "repo/a.txt"}))
        assert out == body  # byte-identical, trailing newline kept

    async def test_window_header_and_slice(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("l1\nl2\nl3\nl4\nl5\n", encoding="utf-8")
        out = await _belt(workdir).call(
            ToolCall("1", "read_file", {"path": "repo/a.txt", "offset": 2, "limit": 2})
        )
        assert out.startswith("[repo/a.txt: 第 2-3 行 / 共 5 行]\n")
        assert out.endswith("l2\nl3")

    async def test_limit_zero_reads_to_end(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("l1\nl2\nl3\n", encoding="utf-8")
        out = await _belt(workdir).call(
            ToolCall("1", "read_file", {"path": "repo/a.txt", "offset": 2, "limit": 0})
        )
        assert "第 2-3 行 / 共 3 行" in out

    async def test_offset_past_end_reports_empty(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("l1\n", encoding="utf-8")
        out = await _belt(workdir).call(
            ToolCall("1", "read_file", {"path": "repo/a.txt", "offset": 9})
        )
        assert "(空" in out

    async def test_bad_window_is_argument_error(self, workdir) -> None:
        belt = _belt(workdir)
        out = await belt.call(ToolCall("1", "read_file", {"path": "repo/a.txt", "offset": 0}))
        assert out.startswith("[参数错误]")
        out = await belt.call(ToolCall("1", "read_file", {"path": "repo/a.txt", "limit": -1}))
        assert out.startswith("[参数错误]")

    async def test_directory_is_argument_error(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "read_file", {"path": "repo"}))
        assert out.startswith("[参数错误]")

    async def test_missing_file_reports(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "read_file", {"path": "repo/nope.txt"}))
        assert out.startswith("[失败]")

    async def test_max_chars_truncates(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("0123456789", encoding="utf-8")
        out = await _belt(workdir).call(
            ToolCall("1", "read_file", {"path": "repo/a.txt", "max_chars": 4})
        )
        assert out == "0123\n…[截断]"

    async def test_negative_max_chars_is_argument_error(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("0123456789", encoding="utf-8")
        out = await _belt(workdir).call(
            ToolCall("1", "read_file", {"path": "repo/a.txt", "max_chars": -1})
        )
        assert out.startswith("[参数错误]")


class TestEditFile:
    async def test_unique_replace(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("hello world\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1", "edit_file", {"path": "repo/a.txt", "old_text": "world", "new_text": "there"}
            )
        )
        assert json.loads(out)["replacements"] == 1
        assert (workdir / "repo" / "a.txt").read_text(encoding="utf-8") == "hello there\n"

    async def test_ambiguous_default_fails_unchanged(self, workdir) -> None:
        body = "x=1\nx=2\n"
        (workdir / "repo" / "a.txt").write_text(body, encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit_file", {"path": "repo/a.txt", "old_text": "x=", "new_text": "y="})
        )
        assert out.startswith("[失败]")
        assert (workdir / "repo" / "a.txt").read_text(encoding="utf-8") == body

    async def test_count_covers_exact_matches(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("x=1\nx=2\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit_file",
                {"path": "repo/a.txt", "old_text": "x=", "new_text": "y=", "count": 2},
            )
        )
        assert json.loads(out)["replacements"] == 2
        assert (workdir / "repo" / "a.txt").read_text(encoding="utf-8") == "y=1\ny=2\n"

    async def test_count_below_matches_fails(self, workdir) -> None:
        body = "x=1\nx=2\nx=3\n"
        (workdir / "repo" / "a.txt").write_text(body, encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit_file",
                {"path": "repo/a.txt", "old_text": "x=", "new_text": "y=", "count": 2},
            )
        )
        assert out.startswith("[失败]")
        assert (workdir / "repo" / "a.txt").read_text(encoding="utf-8") == body

    async def test_no_match_reports(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("abc\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit_file", {"path": "repo/a.txt", "old_text": "zzz", "new_text": "y"})
        )
        assert out.startswith("[失败]")

    async def test_empty_old_text_is_argument_error(self, workdir) -> None:
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit_file", {"path": "repo/a.txt", "old_text": "", "new_text": "y"})
        )
        assert out.startswith("[参数错误]")

    async def test_missing_args_rejected_by_pipeline(self, workdir) -> None:
        out = await _belt(workdir).call(
            ToolCall("1", "edit_file", {"path": "repo/a.txt", "old_text": "x"})
        )
        assert out.startswith("[参数错误]")

    async def test_missing_file_reports(self, workdir) -> None:
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit_file", {"path": "repo/nope.txt", "old_text": "x", "new_text": "y"})
        )
        assert out.startswith("[失败]")

    async def test_binary_refused(self, workdir) -> None:
        (workdir / "repo" / "b.bin").write_bytes(b"\x00\x01abc")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit_file", {"path": "repo/b.bin", "old_text": "abc", "new_text": "y"})
        )
        assert out.startswith("[失败]")

    async def test_skills_tree_denied_by_policy(self, workdir) -> None:
        keep = workdir / "skills" / "keep" / "SKILL.md"
        keep.parent.mkdir(parents=True)
        keep.write_text("# keep\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit_file",
                {"path": "skills/keep/SKILL.md", "old_text": "keep", "new_text": "pwn"},
            )
        )
        assert out.startswith("[已拒绝]")
        assert keep.read_text(encoding="utf-8") == "# keep\n"

    async def test_crlf_round_trips_byte_identical(self, workdir) -> None:
        """Windows CRLF files must not gain extra carriage returns: the write
        path performs no newline translation outside the replaced span."""
        target = workdir / "repo" / "win.txt"
        target.write_bytes(b"hello world\r\nsecond\r\n")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1", "edit_file", {"path": "repo/win.txt", "old_text": "world", "new_text": "there"}
            )
        )
        assert json.loads(out)["replacements"] == 1
        assert target.read_bytes() == b"hello there\r\nsecond\r\n"
