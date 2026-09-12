"""Tests for clients: discovering packages/*/service.json, external
MCP config validation, and the empty pool.
"""

import json
from pathlib import Path

import pytest
from agent.clients import McpClientPool, discover_services, validate_server_config

REPO_ROOT = Path(__file__).parents[2]


class TestDiscovery:
    def test_discovers_real_services(self) -> None:
        cards = discover_services(REPO_ROOT / "packages")
        names = {c["name"] for c in cards}
        assert "notes" in names
        assert "_template" not in names  # underscore directories are not services
        assert "gateway" not in names  # composition shell, not an agent-facing domain
        notes = next(c for c in cards if c["name"] == "notes")
        assert notes["port"] == 8020  # service card fields pass through verbatim

    def test_template_and_missing_card_skipped(self, tmp_path) -> None:
        good = tmp_path / "alpha"
        good.mkdir()
        (good / "service.json").write_text(
            json.dumps({"name": "alpha", "port": 1}), encoding="utf-8"
        )
        (tmp_path / "_template").mkdir()
        (tmp_path / "empty").mkdir()  # directory without a card: skipped, no crash
        assert [c["name"] for c in discover_services(tmp_path)] == ["alpha"]

    def test_bad_json_skipped(self, tmp_path) -> None:
        bad = tmp_path / "beta"
        bad.mkdir()
        (bad / "service.json").write_text("{broken", encoding="utf-8")
        assert discover_services(tmp_path) == []


class TestPool:
    def test_pool_starts_empty(self) -> None:
        """An empty pool is a valid steady state: with no external MCP configs, list_state is empty and the Toolbelt gets no tools."""
        pool = McpClientPool()
        assert pool.list_state() == []
        assert pool.configs() == []

    def test_validate_rejects_bad_config(self) -> None:
        """Invalid configs (id shape / file: URL / empty command) are rejected at the entry point."""
        from platform_contracts import ServiceError

        with pytest.raises(ServiceError):
            validate_server_config({"id": "Bad_Id", "kind": "stdio", "command": "npx"})
        with pytest.raises(ServiceError):
            validate_server_config({"id": "ok", "kind": "url", "url": "file:///etc"})
        with pytest.raises(ServiceError):
            validate_server_config({"id": "ok", "kind": "stdio", "command": ""})
        # Valid shape: all fields present after normalization
        cfg = validate_server_config(
            {"id": "demo", "kind": "stdio", "command": "npx", "args": ["-y", "x"]}
        )
        assert cfg["name"] == "demo" and cfg["approval"] == "item" and cfg["enabled"]
