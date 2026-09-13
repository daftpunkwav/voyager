"""Unit tests for the edit_file fuzzy match chain: each level's match and
rejection semantics, ambiguity reporting, and span fidelity.
"""

from agent.tools.workspace.edit_matchers import locate, reindent


class TestExact:
    def test_unique_span(self) -> None:
        result = locate("a b c", "b")
        assert result.span == (2, 3)
        assert result.level == "exact"

    def test_absent(self) -> None:
        result = locate("abc", "zzz")
        assert result.span is None
        assert result.ambiguous == 0


class TestLineTrimmed:
    def test_trailing_whitespace_line_matches(self) -> None:
        result = locate("a \nb\nc\n", "a\nb\n")
        assert result.level == "line_trimmed"
        assert result.span == (0, 5)

    def test_trailing_newline_matches_at_eof_without_one(self) -> None:
        # file's last line has no terminator: the peeled trailing "" has
        # nothing to consume, the span just stops at the content end
        result = locate("a\nb", "a\nb\n")
        assert result.level == "line_trimmed"
        assert result.span == (0, 3)

    def test_leading_newline_consumes_preceding_terminator(self) -> None:
        assert locate("a\nb\n", "\nb\n").span == (1, 4)
        assert locate("a\n\nb\n", "\nb\n").span == (2, 5)

    def test_indent_capture_for_unindented_old(self) -> None:
        result = locate("def f():\n    return 1 \n", "return 1\n")
        assert result.level == "line_trimmed"
        assert result.span == (9, 23)
        assert result.line_indent == "    "

    def test_no_indent_capture_when_old_is_indented(self) -> None:
        result = locate("def f():\n    return 1\n", "    return 1\n")
        assert result.level == "exact"  # exact hit wins; nothing to capture

    def test_two_candidates_ambiguous(self) -> None:
        result = locate("alpha\nx\nalpha\n", "alpha")
        assert result.span is None
        assert result.ambiguous == 2


class TestBlockAnchor:
    body = "head\none\ntwo\nthree\ntail\n"

    def test_slightly_changed_middle_line(self) -> None:
        old = "head\none\ntwo!\nthree\ntail"
        result = locate(self.body, old)
        assert result.level == "block_anchor"
        assert result.span == (0, len(self.body) - 1)  # final \n excluded

    def test_reorders_within_similarity_are_accepted(self) -> None:
        old = "head\none\nthree\ntwo\ntail"
        assert locate(self.body, old).level == "block_anchor"

    def test_disproportionate_window_rejected(self) -> None:
        old = "head\none\ntail"  # 3 lines; only a 3-line window could match
        text = "head\none\nx\ny\nz\nw\nv\ntail\n"
        assert locate(text, old).span is None

    def test_two_candidates_ambiguous(self) -> None:
        text = "head\none\ntwo!\nthree\ntail\nhead\none\ntwo!\nthree\ntail\n"
        old = "head\none\ntwo!\nthree\ntail"
        result = locate(text, old)
        assert result.span is None
        assert result.ambiguous == 2


class TestWhitespace:
    def test_lf_old_matches_crlf_text(self) -> None:
        # full-line matching is line-ending blind, so the LF needle lands on
        # the CRLF file already at the line_trimmed level; the trailing ""
        # consumes the file's final terminator (restored by the caller)
        result = locate("a\r\nb\r\n", "a\nb\n")
        assert result.level == "line_trimmed"
        assert result.span == (0, 6)
        assert result.consumed_eol is True

    def test_inner_whitespace_old_needs_the_ws_level_on_crlf(self) -> None:
        result = locate("a\r\nb\r\n", "a  b")
        assert result.level == "whitespace"
        assert result.span == (0, 4)  # no trailing newline: terminator untouched

    def test_collapsed_runs(self) -> None:
        result = locate("x  =\t1\ny\n", "x = 1")
        assert result.level == "whitespace"
        assert result.span == (0, 6)

    def test_ambiguous_reports_count(self) -> None:
        result = locate("a b\na b\n", "a\tb")
        assert result.span is None
        assert result.ambiguous == 2


class TestEscape:
    def test_literal_backslash_n_matches_real_newline(self) -> None:
        result = locate("line1\nline2\n", "line1\\nline2")
        assert result.level == "escape"
        assert result.span == (0, 11)

    def test_no_escapes_is_skipped_not_found(self) -> None:
        assert locate("abc", "abc").level == "exact"


class TestChainOrdering:
    def test_least_degraded_level_wins(self) -> None:
        # exact applies before line_trimmed even though both would match
        assert locate("alpha\n", "alpha").level == "exact"

    def test_ambiguity_does_not_block_a_degraded_unique_match(self) -> None:
        # exact finds 2 candidates ("x = 1" inside "x = 11" too); the chain
        # keeps degrading and accepts the unique full-line match
        result = locate("x = 11\nx = 1\n", "x = 1")
        assert result.level == "line_trimmed"
        assert result.span == (7, 12)


def test_reindent_prepends_to_non_empty_lines() -> None:
    assert reindent("x = 1\ny = 2", "    ") == "    x = 1\n    y = 2"
    assert reindent("a\n\nb", "\t") == "\ta\n\n\tb"  # blank lines stay blank
    assert reindent("x", "") == "x"
