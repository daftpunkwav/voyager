"""Tests for the page context registry: per-page summaries reported by the
web app, rendered into the per-turn volatile context block."""

from agent.context import PageContextRegistry


class TestPages:
    def test_update_and_render(self) -> None:
        pages = PageContextRegistry()
        assert "未知" in pages.render()
        pages.update(
            "notes", "36 notes, document A open", counts={"notes": 36}, selected="paragraph 3"
        )
        pages.update("graph", "120 nodes", counts={"nodes": 120})
        current = pages.current()
        assert current is not None  # most recently reported page is current
        assert current.page == "graph"
        text = pages.render()
        assert "graph" in text and "nodes=120" in text
