"""Pure-function tests for highlight marks: superset-selection flattening,
fence skipping, visible-text matching.
"""

import pytest
from notes.marks import (
    MarkError,
    apply_in_range,
    apply_note_mark,
    find_marks,
    normalize_tone,
    parse_mark,
    scan_marks,
)


def test_parse_toned_and_bare() -> None:
    assert parse_mark("==cool:中间件==") == ("cool", "中间件")
    assert parse_mark("==中间件==") == ("warm", "中间件")
    assert parse_mark("==violet:紫==") == ("violet", "紫")
    assert parse_mark("==rgb7c3aed:自定义==") == ("rgb7c3aed", "自定义")
    assert parse_mark("普通") is None


def test_normalize_custom_rgb() -> None:
    assert normalize_tone("#7C3AED") == "rgb7c3aed"
    assert normalize_tone("7c3aed") == "rgb7c3aed"
    assert normalize_tone("sand") == "sand"
    with pytest.raises(MarkError):
        normalize_tone("not-a-color")


def test_apply_custom_rgb_and_named() -> None:
    assert apply_note_mark("词", "词", "#7c3aed") == "==rgb7c3aed:词=="
    assert apply_note_mark("==rgb7c3aed:词==", "词", "clear") == "词"


def test_wrap_multiline_and_list() -> None:
    assert apply_note_mark("第一段\n\n第二段", "第一段\n\n第二段", "cool") == (
        "==cool:第一段==\n\n==cool:第二段=="
    )
    assert apply_note_mark("- aa\n- bb", "- aa\n- bb", "rose") == ("- ==rose:aa==\n- ==rose:bb==")


def test_superset_selection_flattens_nested() -> None:
    out = apply_in_range("aaa==warm:bbb==ccc", 0, len("aaa==warm:bbb==ccc"), "cool")
    assert out == "==cool:aaabbbccc=="
    assert "==warm:" not in out


def test_inner_recolor_splits_three() -> None:
    doc = "==warm:AAABBBCCC=="
    start = doc.index("BBB")
    out = apply_in_range(doc, start, start + 3, "cool")
    assert out == "==warm:AAA====cool:BBB====warm:CCC=="
    assert [m.tone for m in find_marks(out)] == ["warm", "cool", "warm"]


def test_skip_fenced_code() -> None:
    content = "```\nhello\n```\n\nhello body"
    out = apply_note_mark(content, "hello", "warm")
    assert out.startswith("```\nhello\n```")
    assert "==warm:hello== body" in out


def test_clear_strips_unclosed_tone_prefix_in_body() -> None:
    assert (
        apply_in_range("==rose:hello\nworld", 0, len("==rose:hello\nworld"), "clear")
        == "hello\nworld"
    )


def test_clear_strips_unclosed_tone_prefix_in_fence() -> None:
    doc = "```\n==rose:+-----+\n==rose:| box |\n==rose:+-----+\n```\n"
    out = apply_in_range(doc, 0, len(doc), "clear")
    assert "==rose:" not in out
    assert "| box |" in out


def test_clear_strips_marks_inside_fence() -> None:
    doc = "```\n==rose:| gateway |\n==\n```\nbody"
    out = apply_in_range(doc, 0, len(doc), "clear")
    assert "==rose:" not in out
    assert "| gateway |" in out


def test_quote_matches_visible_inside_mark() -> None:
    content = "先看==cool:中间件==再看编排"
    out = apply_note_mark(content, "中间件", "rose")
    assert out == "先看==rose:中间件==再看编排"
    cleared = apply_note_mark(out, "中间件", "clear")
    assert cleared == "先看中间件再看编排"


def test_equals_line_is_not_a_mark() -> None:
    assert scan_marks("=======") == []


def test_long_fence_not_closed_by_shorter() -> None:
    doc = "````\nconst x = 1\n```\nstill code\n````\n正文"
    start = doc.index("still")
    out = apply_in_range(doc, start, start + 10, "rose")
    assert "==rose:still" not in out
    assert "==rose:正文==" in apply_note_mark(doc, "正文", "rose")


def test_clear_keeps_literal_equals_in_fence() -> None:
    doc = '```\nconst pattern = "==a=="\n```\n'
    out = apply_in_range(doc, 0, len(doc), "clear")
    assert 'const pattern = "==a=="' in out


def test_skip_inline_code() -> None:
    doc = "see `hello` please hello"
    start = doc.index("hello")
    skipped = apply_in_range(doc, start, start + 5, "warm")
    assert "`hello`" in skipped
    assert "==warm:hello==" not in skipped
    out = apply_note_mark(doc, "hello", "warm")
    assert "`hello` please ==warm:hello==" in out


def test_wrap_line_keeps_inline_code_inside_mark() -> None:
    assert apply_in_range("行内 `hello` 外面", 0, len("行内 `hello` 外面"), "cool") == (
        "==cool:行内 `hello` 外面=="
    )


def test_skip_ascii_box_and_table_rows() -> None:
    box = "+-----+\n| box |\n+-----+"
    assert apply_in_range(box, 0, len(box), "rose") == box
    table = "| a | b |\n| - | - |\n| c | d |"
    assert apply_in_range(table, 0, len(table), "cool") == table
    cell = "| hello |"
    start = cell.index("hello")
    assert apply_in_range(cell, start, start + 5, "lime") == "| ==lime:hello== |"
