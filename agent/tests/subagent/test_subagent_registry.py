"""Tests for the user-defined subagent registry: validation, save/load,
listing, and deletion.
"""

import json

import pytest
from agent.subagent.registry import SubagentDef, SubagentRegistry
from platform_contracts import ServiceError


class TestDef:
    def test_valid_definition(self) -> None:
        d = SubagentDef(
            name="translator", description="translate", mode="cot", allowed_tools=("read_file",)
        )
        assert d.trigger == "manual"

    def test_bad_name_rejected(self) -> None:
        with pytest.raises(ServiceError, match="snake_case"):
            SubagentDef(name="Bad Name", description="x")

    def test_unknown_mode_rejected(self) -> None:
        with pytest.raises(ServiceError, match="unknown mode"):
            SubagentDef(name="ok_name", description="x", mode="magic")


class TestRegistry:
    def test_save_load_list_delete(self, tmp_path) -> None:
        reg = SubagentRegistry(tmp_path)
        reg.save(SubagentDef(name="alpha", description="A", mode="react"))
        reg.save(SubagentDef(name="beta", description="B", mode="tot", scopes=("notes.read",)))
        loaded = reg.load("beta")
        assert loaded.mode == "tot" and loaded.scopes == ("notes.read",)
        assert [d.name for d in reg.list()] == ["alpha", "beta"]
        reg.delete("alpha")
        assert [d.name for d in reg.list()] == ["beta"]

    def test_load_unknown_raises(self, tmp_path) -> None:
        with pytest.raises(ServiceError, match="unregistered"):
            SubagentRegistry(tmp_path).load("ghost")

    def test_load_delete_reject_traversal(self, tmp_path) -> None:
        # A valid-shaped JSON sits outside the root; `../pwn` must not be able to read or delete it
        (tmp_path / "pwn.json").write_text(
            json.dumps({"name": "pwn", "description": "x", "mode": "react"}),
            encoding="utf-8",
        )
        reg = SubagentRegistry(tmp_path / "sub")
        with pytest.raises(ServiceError, match="snake_case"):
            reg.load("../pwn")
        with pytest.raises(ServiceError, match="snake_case"):
            reg.delete("../pwn")
        assert (tmp_path / "pwn.json").exists()

    def test_load_rejects_non_snake_case(self, tmp_path) -> None:
        with pytest.raises(ServiceError, match="snake_case"):
            SubagentRegistry(tmp_path).load("Bad Name")

    def test_list_skips_bad_files(self, tmp_path) -> None:
        # A broken JSON / invalid definition must not block list(); bad files stay on disk
        (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
        reg = SubagentRegistry(tmp_path)
        reg.save(SubagentDef(name="alpha", description="A", mode="react"))
        (tmp_path / "zzz-bad-mode.json").write_text(
            json.dumps({"name": "zzz", "description": "x", "mode": "magic"}),
            encoding="utf-8",
        )
        assert [d.name for d in reg.list()] == ["alpha"]
        # Bad files are neither deleted nor modified
        assert (tmp_path / "broken.json").read_text(encoding="utf-8") == "{not json"
        assert (tmp_path / "zzz-bad-mode.json").exists()
