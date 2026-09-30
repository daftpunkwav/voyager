"""Tests for the dev launcher's single-instance lock: a second `python -m
host.dev` against the same data/runtime must refuse to start (double-running
the durable queue/cron jobs would race the same SQLite files), and the lock
must be re-acquirable once the first instance releases it."""

import os

import pytest
from host import dev


class TestInstanceLock:
    def test_second_instance_refused_then_reacquirable(self, tmp_path, monkeypatch) -> None:
        """First acquire succeeds and stamps the pid; a second concurrent
        acquire exits with the actionable message; after the holder releases,
        the lock is acquirable again (a crashed-and-restarted launcher works)."""
        monkeypatch.setattr(dev, "ROOT", tmp_path)
        monkeypatch.setattr(dev, "_LOCK_HANDLE", None)
        lock_path = tmp_path / "data" / "runtime" / "host.lock"

        dev._acquire_instance_lock()
        try:
            assert dev._LOCK_HANDLE is not None
            assert lock_path.is_file()  # data/runtime/ is created on demand

            with pytest.raises(SystemExit, match="another host.dev instance"):
                dev._acquire_instance_lock()

            # Release and take it again: exit/crash of the holder must not
            # wedge the launcher for later runs.
            dev._LOCK_HANDLE.close()
            dev._LOCK_HANDLE = None
            dev._acquire_instance_lock()
            assert dev._LOCK_HANDLE is not None
        finally:
            if dev._LOCK_HANDLE is not None:  # never leak the handle into tmp cleanup
                dev._LOCK_HANDLE.close()
                dev._LOCK_HANDLE = None
        # The holder stamps its pid (readable once the byte-0 lock is released;
        # Windows denies reads of the locked range while held).
        assert f"pid={os.getpid()}" in lock_path.read_text(encoding="utf-8")
