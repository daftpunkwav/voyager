"""Shared fixtures for the tools/ test package."""

import pytest
from agent.tools import ensure_workdir


@pytest.fixture()
def workdir(tmp_path):
    root = ensure_workdir(tmp_path / "workspace")
    return root
