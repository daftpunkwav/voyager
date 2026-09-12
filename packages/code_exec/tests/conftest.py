"""Keep code_exec tests hermetic: never spawn the host's docker CLI.

The executor probes shutil.which("docker") and, when found, runs snippets in a
one-shot container from a background task. On a machine whose Docker Desktop is
stopped the CLI can block for minutes, which stalls the whole pytest session at
teardown. Tests therefore exercise the host-fallback path; set
CODE_EXEC_TEST_DOCKER=1 to run them against the real docker CLI.
"""

import os

import pytest
from code_exec import executor


@pytest.fixture(autouse=True)
def _no_host_docker(monkeypatch):
    if os.environ.get("CODE_EXEC_TEST_DOCKER") == "1":
        return
    monkeypatch.setattr(executor.shutil, "which", lambda name: None)
