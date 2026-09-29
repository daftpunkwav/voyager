"""Tests for secure_data_dir: the standalone MCP data-directory jail."""

import os
import stat

import pytest
from platform_capability import runtime_dir as runtime_dir_module
from platform_capability import secure_data_dir

IS_POSIX = os.name != "nt"


@pytest.fixture()
def temp_root(tmp_path, monkeypatch):
    """Point the helper at a scratch temp dir so tests never touch the real
    per-user temp area."""
    monkeypatch.setattr(runtime_dir_module, "gettempdir", lambda: str(tmp_path))
    return tmp_path


def test_creates_missing_dir_owner_only(temp_root):
    path = secure_data_dir("x-mcp")
    assert path == temp_root / "x-mcp"
    assert path.is_dir()
    if IS_POSIX:
        assert stat.S_IMODE(path.stat().st_mode) & 0o077 == 0


def test_returns_existing_owned_dir_and_tightens_perms(temp_root):
    existing = temp_root / "x-mcp"
    existing.mkdir()
    if IS_POSIX:
        os.chmod(existing, 0o755)  # legacy umask artifact
    assert secure_data_dir("x-mcp") == existing
    if IS_POSIX:
        assert stat.S_IMODE(existing.stat().st_mode) & 0o077 == 0


def test_refuses_non_directory(temp_root):
    (temp_root / "x-mcp").write_text("not a dir", encoding="utf-8")
    with pytest.raises(RuntimeError, match="not a plain directory"):
        secure_data_dir("x-mcp")


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_refuses_symlink(temp_root):
    outside = temp_root / "outside"
    outside.mkdir()
    (temp_root / "x-mcp").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RuntimeError, match="not a plain directory"):
        secure_data_dir("x-mcp")


@pytest.mark.skipif(not hasattr(os, "getuid"), reason="uid checks are Unix-only")
def test_refuses_foreign_owned_dir(temp_root, monkeypatch):
    target = temp_root / "x-mcp"
    target.mkdir()
    real_uid = os.getuid()  # type: ignore[attr-defined]  # Unix-only (skipped above)
    monkeypatch.setattr(os, "getuid", lambda: real_uid + 1)
    with pytest.raises(RuntimeError, match="owned by another user"):
        secure_data_dir("x-mcp")
