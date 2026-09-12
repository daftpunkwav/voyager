"""ScopedRules: AGENTS.md under the task root becomes a rule layer; missing,
unreadable, oversized and out-of-root files are handled deterministically."""

from __future__ import annotations

import os

import pytest
from agent.context.builder import ContextBuilder
from agent.context.scoped_rules import ScopedRules


class TestScopedRules:
    def test_missing_is_empty_and_present_is_injected(self, tmp_path) -> None:
        rules = ScopedRules(tmp_path)
        assert rules.render() == ""
        (tmp_path / "AGENTS.md").write_text("- always answer in Chinese\n", encoding="utf-8")
        assert "always answer in Chinese" in rules.render()
        system = ContextBuilder(scoped_rules=rules).system()
        assert "【目录规则 AGENTS.md】" in system and "always answer in Chinese" in system

    def test_truncation_and_mtime_cache(self, tmp_path) -> None:
        path = tmp_path / "AGENTS.md"
        path.write_text("x" * 100, encoding="utf-8")
        rules = ScopedRules(tmp_path, max_chars=20)
        first = rules.render()
        assert first.startswith("x" * 20) and "截断" in first
        path.write_text("fresh rules", encoding="utf-8")
        os.utime(path, None)
        assert rules.render() == "fresh rules"

    @pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
    def test_symlink_outside_root_is_ignored(self, tmp_path) -> None:
        outside = tmp_path / "outside.md"
        outside.write_text("leak", encoding="utf-8")
        root = tmp_path / "root"
        root.mkdir()
        (root / "AGENTS.md").symlink_to(outside)
        assert ScopedRules(root).render() == ""
