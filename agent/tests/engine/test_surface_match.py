"""Allowlist-vs-surface matching (dispatch-time narrowing): prefix grants,
exact names, the miss report and the frozen intersection — including the
empty-set and unknown-category-deny boundaries.

Test type: unit (pure functions).
"""

from __future__ import annotations

from agent.engine.surface import entry_matches, intersect_surface, surface_misses

SURFACE = ("read_file", "write_file", "web_search", "notes__create_note")


class TestEntryMatches:
    def test_exact_name_only_matches_itself(self) -> None:
        assert entry_matches("read_file", "read_file") is True
        assert entry_matches("read_file", "read_fil") is False
        assert entry_matches("read_file", "read_file_extra") is False

    def test_trailing_star_is_a_prefix_grant(self) -> None:
        assert entry_matches("write_file", "write_*") is True
        assert entry_matches("notes__create_note", "notes__*") is True
        assert entry_matches("web_search", "notes__*") is False

    def test_single_trailing_star_is_not_a_prefix(self) -> None:
        """A bare '*' is matched literally (len>1 guard), granting nothing."""
        assert entry_matches("read_file", "*") is False

    def test_star_inside_the_name_is_literal(self) -> None:
        assert entry_matches("a*b", "a*b") is True
        assert entry_matches("axb", "a*b") is False


class TestSurfaceMisses:
    def test_entries_with_no_availability_are_reported(self) -> None:
        misses = surface_misses(["read_file", "shell__run"], SURFACE)
        assert misses == ["shell__run"]

    def test_prefix_entry_available_when_any_name_matches(self) -> None:
        assert surface_misses(["web_*"], SURFACE) == []
        assert surface_misses(["todo_*"], SURFACE) == ["todo_*"]

    def test_empty_entries_have_no_misses(self) -> None:
        assert surface_misses([], SURFACE) == []

    def test_everything_misses_an_empty_surface(self) -> None:
        """The unknown-category / empty-surface boundary: nothing can be
        offered, so every entry is a miss (deny by construction)."""
        assert surface_misses(["read_file", "web_*"], []) == ["read_file", "web_*"]


class TestIntersectSurface:
    def test_keeps_available_names_covered_by_any_entry(self) -> None:
        out = intersect_surface(["read_file", "web_*"], SURFACE)
        assert out == ("read_file", "web_search")

    def test_result_follows_the_surface_order_not_the_entry_order(self) -> None:
        out = intersect_surface(["web_*", "read_file"], ("web_search", "read_file"))
        assert out == ("web_search", "read_file")

    def test_empty_entries_freeze_to_nothing(self) -> None:
        assert intersect_surface([], SURFACE) == ()

    def test_empty_surface_freezes_to_nothing(self) -> None:
        """A narrowed instance dispatching on an empty surface grants an empty
        child surface: narrowing can never widen."""
        assert intersect_surface(["read_file", "web_*"], ()) == ()
