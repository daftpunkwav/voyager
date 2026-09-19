"""Tests for atomic file editing (edit) and windowed reading
(read offset/limit): uniqueness guard, caps, error paths, and
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
        out = await _belt(workdir).call(ToolCall("1", "read", {"path": "repo/a.txt"}))
        assert out == body  # byte-identical, trailing newline kept

    async def test_window_header_and_slice(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("l1\nl2\nl3\nl4\nl5\n", encoding="utf-8")
        out = await _belt(workdir).call(
            ToolCall("1", "read", {"path": "repo/a.txt", "offset": 2, "limit": 2})
        )
        assert out.startswith("[repo/a.txt: 第 2-3 行 / 共 5 行]\n")
        assert out.endswith("l2\nl3")

    async def test_limit_zero_reads_to_end(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("l1\nl2\nl3\n", encoding="utf-8")
        out = await _belt(workdir).call(
            ToolCall("1", "read", {"path": "repo/a.txt", "offset": 2, "limit": 0})
        )
        assert "第 2-3 行 / 共 3 行" in out

    async def test_offset_past_end_reports_empty(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("l1\n", encoding="utf-8")
        out = await _belt(workdir).call(ToolCall("1", "read", {"path": "repo/a.txt", "offset": 9}))
        assert "(空" in out

    async def test_bad_window_is_argument_error(self, workdir) -> None:
        belt = _belt(workdir)
        out = await belt.call(ToolCall("1", "read", {"path": "repo/a.txt", "offset": 0}))
        assert out.startswith("[参数错误]")
        out = await belt.call(ToolCall("1", "read", {"path": "repo/a.txt", "limit": -1}))
        assert out.startswith("[参数错误]")

    async def test_directory_is_argument_error(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "read", {"path": "repo"}))
        assert out.startswith("[参数错误]")

    async def test_missing_file_reports(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "read", {"path": "repo/nope.txt"}))
        assert out.startswith("[失败]")

    async def test_max_chars_truncates(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("0123456789", encoding="utf-8")
        out = await _belt(workdir).call(
            ToolCall("1", "read", {"path": "repo/a.txt", "max_chars": 4})
        )
        assert out == "0123\n…[截断]"

    async def test_negative_max_chars_is_argument_error(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("0123456789", encoding="utf-8")
        out = await _belt(workdir).call(
            ToolCall("1", "read", {"path": "repo/a.txt", "max_chars": -1})
        )
        assert out.startswith("[参数错误]")


class TestEditFile:
    async def test_unique_replace(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("hello world\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit", {"path": "repo/a.txt", "old_text": "world", "new_text": "there"})
        )
        assert json.loads(out)["replacements"] == 1
        assert (workdir / "repo" / "a.txt").read_text(encoding="utf-8") == "hello there\n"

    async def test_ambiguous_default_fails_unchanged(self, workdir) -> None:
        body = "x=1\nx=2\n"
        (workdir / "repo" / "a.txt").write_text(body, encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit", {"path": "repo/a.txt", "old_text": "x=", "new_text": "y="})
        )
        assert out.startswith("[失败]")
        assert (workdir / "repo" / "a.txt").read_text(encoding="utf-8") == body

    async def test_count_covers_exact_matches(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("x=1\nx=2\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit",
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
                "edit",
                {"path": "repo/a.txt", "old_text": "x=", "new_text": "y=", "count": 2},
            )
        )
        assert out.startswith("[失败]")
        assert (workdir / "repo" / "a.txt").read_text(encoding="utf-8") == body

    async def test_no_match_reports(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("abc\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit", {"path": "repo/a.txt", "old_text": "zzz", "new_text": "y"})
        )
        assert out.startswith("[失败]")

    async def test_empty_old_text_is_argument_error(self, workdir) -> None:
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit", {"path": "repo/a.txt", "old_text": "", "new_text": "y"})
        )
        assert out.startswith("[参数错误]")

    async def test_missing_args_rejected_by_pipeline(self, workdir) -> None:
        out = await _belt(workdir).call(
            ToolCall("1", "edit", {"path": "repo/a.txt", "old_text": "x"})
        )
        assert out.startswith("[参数错误]")

    async def test_missing_file_reports(self, workdir) -> None:
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit", {"path": "repo/nope.txt", "old_text": "x", "new_text": "y"})
        )
        assert out.startswith("[失败]")

    async def test_binary_refused(self, workdir) -> None:
        (workdir / "repo" / "b.bin").write_bytes(b"\x00\x01abc")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit", {"path": "repo/b.bin", "old_text": "abc", "new_text": "y"})
        )
        assert out.startswith("[失败]")

    async def test_skills_tree_denied_by_policy(self, workdir) -> None:
        keep = workdir / "skills" / "keep" / "SKILL.md"
        keep.parent.mkdir(parents=True)
        keep.write_text("# keep\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit",
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
                "1", "edit", {"path": "repo/win.txt", "old_text": "world", "new_text": "there"}
            )
        )
        assert json.loads(out)["replacements"] == 1
        assert target.read_bytes() == b"hello there\r\nsecond\r\n"

    async def test_exact_result_reports_matched_by(self, workdir) -> None:
        (workdir / "repo" / "a.txt").write_text("hello world\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit", {"path": "repo/a.txt", "old_text": "world", "new_text": "there"})
        )
        assert json.loads(out)["matched_by"] == "exact"

    async def test_fuzzy_line_trim_reindents(self, workdir) -> None:
        target = workdir / "repo" / "code.py"
        target.write_text("def f():\n    return 1 \n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit",
                {"path": "repo/code.py", "old_text": "return 1\n", "new_text": "return 2"},
            )
        )
        body = json.loads(out)
        assert body["matched_by"] == "line_trimmed"
        # the matched line's indentation is carried onto the replacement
        assert target.read_text(encoding="utf-8") == "def f():\n    return 2\n"

    async def test_fuzzy_whitespace_lf_old_on_crlf_file(self, workdir) -> None:
        target = workdir / "repo" / "win.txt"
        target.write_bytes(b"a\r\nb\r\nc\r\n")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit", {"path": "repo/win.txt", "old_text": "a\nb", "new_text": "x\ny"})
        )
        body = json.loads(out)
        assert body["matched_by"] == "line_trimmed"
        # new_text is aligned to the file's CRLF convention
        assert target.read_bytes() == b"x\r\ny\r\nc\r\n"

    async def test_fuzzy_block_anchor_rescues_typo(self, workdir) -> None:
        target = workdir / "repo" / "blk.txt"
        target.write_text("head\none\ntwo\nthree\ntail\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit",
                {
                    "path": "repo/blk.txt",
                    "old_text": "head\none\ntwo!\nthree\ntail",
                    "new_text": "head\none\ntwo\nthree\ntail!",
                },
            )
        )
        body = json.loads(out)
        assert body["matched_by"] == "block_anchor"
        assert target.read_text(encoding="utf-8") == "head\none\ntwo\nthree\ntail!\n"

    async def test_fuzzy_ambiguous_fails_unchanged(self, workdir) -> None:
        body = "a b\na b\n"
        (workdir / "repo" / "amb.txt").write_text(body, encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall("1", "edit", {"path": "repo/amb.txt", "old_text": "a\tb", "new_text": "z"})
        )
        assert out.startswith("[失败]")
        assert "候选" in out
        assert (workdir / "repo" / "amb.txt").read_text(encoding="utf-8") == body

    async def test_fuzzy_escape_level(self, workdir) -> None:
        target = workdir / "repo" / "esc.txt"
        target.write_text("line1\nline2\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit",
                {"path": "repo/esc.txt", "old_text": "line1\\nline2", "new_text": "oneline"},
            )
        )
        body = json.loads(out)
        assert body["matched_by"] == "escape"
        assert target.read_text(encoding="utf-8") == "oneline\n"

    async def test_fuzzy_count_is_exact_only(self, workdir) -> None:
        # count > 1 keeps the strict literal semantics; the fuzzy ladder
        # never silently replaces several sites
        (workdir / "repo" / "cnt.txt").write_text("a \nb\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit",
                {"path": "repo/cnt.txt", "old_text": "a\nb", "new_text": "z", "count": 2},
            )
        )
        assert out.startswith("[失败]")
        assert (workdir / "repo" / "cnt.txt").read_text(encoding="utf-8") == "a \nb\n"


class TestEditFuzzyRegression:
    """Reviewer-reproduced edge cases: reindent gate must not double-indent a
    pre-indented block that starts with a newline, and the kept line break
    must not defeat newline normalization on CRLF files."""

    async def test_leading_newline_indented_block_not_double_indented(self, workdir) -> None:
        target = workdir / "repo" / "deep.py"
        target.write_text("def f():\n        return x\n", encoding="utf-8")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit",
                {
                    "path": "repo/deep.py",
                    "old_text": "\n        return x\n",
                    "new_text": "\n    return z",
                },
            )
        )
        body = json.loads(out)
        assert body["matched_by"] == "line_trimmed"
        # new_text's own indentation is respected: no file-indent re-application
        assert target.read_text(encoding="utf-8") == "def f():\n    return z\n"

    async def test_crlf_consumed_eol_stays_uniform(self, workdir) -> None:
        target = workdir / "repo" / "win2.txt"
        target.write_bytes(b"alpha\r\nbeta\r\ngamma\r\n")
        out = await _belt(workdir, confirm=_yes).call(
            ToolCall(
                "1",
                "edit",
                {
                    "path": "repo/win2.txt",
                    "old_text": "alpha\nbeta\n",
                    "new_text": "one\ntwo\nthree",
                },
            )
        )
        body = json.loads(out)
        assert body["matched_by"] == "line_trimmed"
        assert target.read_bytes() == b"one\r\ntwo\r\nthree\r\ngamma\r\n"
