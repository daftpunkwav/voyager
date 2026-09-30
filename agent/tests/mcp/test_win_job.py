"""Tests for the Windows Job Object wrapper behind stdio MCP tree teardown.

The assign_tree logic is exercised through a scripted kernel32 fake on every
platform (the real binding is win32-only); the end-to-end tree kill against a
real process tree lives in test_mcp_session.py, Windows-only.

Test type: unit (fake kernel32, no processes).
"""

from __future__ import annotations

from typing import Any

import pytest
from agent.mcp import _win_job
from agent.mcp._win_job import _KILL_ON_JOB_CLOSE, assign_tree

_JOB_HANDLE = 4321
_PROC_HANDLE = 5000


class _FakeK32:
    """Scripted kernel32: returns stable handles, records closes, fails on cue."""

    def __init__(
        self,
        *,
        fail_create: bool = False,
        fail_set: bool = False,
        fail_open: bool = False,
        fail_assign: bool = False,
    ) -> None:
        self.closed: list[int] = []
        self.limit_flags: int | None = None
        self.info_class: int | None = None
        self.assigned: tuple[int, int] | None = None
        self._fail_create = fail_create
        self._fail_set = fail_set
        self._fail_open = fail_open
        self._fail_assign = fail_assign

    def CreateJobObjectW(self, attrs: Any, name: Any) -> int:
        if self._fail_create:
            return 0
        return _JOB_HANDLE

    def SetInformationJobObject(self, job: int, info_class: int, info: Any, size: int) -> int:
        if self._fail_set:
            return 0
        self.info_class = info_class
        # byref() wraps the struct; ._obj reaches it (test-only access)
        self.limit_flags = int(info._obj.BasicLimitInformation.LimitFlags)
        return 1

    def OpenProcess(self, access: int, inherit: int, pid: int) -> int:
        if self._fail_open:
            return 0
        return _PROC_HANDLE + pid

    def AssignProcessToJobObject(self, job: int, proc: int) -> int:
        if self._fail_assign:
            return 0
        self.assigned = (job, proc)
        return 1

    def CloseHandle(self, handle: int) -> int:
        self.closed.append(handle)
        return 1


@pytest.fixture()
def fake_k32(monkeypatch: pytest.MonkeyPatch) -> _FakeK32:
    fake = _FakeK32()
    monkeypatch.setattr(_win_job, "_k32", fake)
    return fake


class TestAssignTree:
    async def test_success_assigns_pid_and_closes_child_handle(self, fake_k32: _FakeK32) -> None:
        job = assign_tree(4242)
        assert job is not None
        assert fake_k32.assigned == (_JOB_HANDLE, _PROC_HANDLE + 4242)
        # the child process handle is released right after the assignment
        assert _PROC_HANDLE + 4242 in fake_k32.closed
        assert _JOB_HANDLE not in fake_k32.closed
        job.close()
        assert _JOB_HANDLE in fake_k32.closed

    async def test_job_carries_kill_on_close_limit(self, fake_k32: _FakeK32) -> None:
        assert assign_tree(1) is not None
        assert fake_k32.info_class == 9  # JobObjectExtendedLimitInformation
        assert fake_k32.limit_flags == _KILL_ON_JOB_CLOSE

    async def test_close_is_idempotent(self, fake_k32: _FakeK32) -> None:
        job = assign_tree(1)
        assert job is not None
        job.close()
        job.close()
        assert fake_k32.closed.count(_JOB_HANDLE) == 1

    async def test_create_failure_degrades_to_none(self, monkeypatch: Any) -> None:
        fake = _FakeK32(fail_create=True)
        monkeypatch.setattr(_win_job, "_k32", fake)
        assert assign_tree(1) is None
        assert fake.closed == []  # nothing was created, nothing to close

    async def test_set_info_failure_closes_job(self, monkeypatch: Any) -> None:
        fake = _FakeK32(fail_set=True)
        monkeypatch.setattr(_win_job, "_k32", fake)
        assert assign_tree(1) is None
        assert fake.closed == [_JOB_HANDLE]

    async def test_open_failure_closes_job(self, monkeypatch: Any) -> None:
        fake = _FakeK32(fail_open=True)
        monkeypatch.setattr(_win_job, "_k32", fake)
        assert assign_tree(1) is None
        assert fake.closed == [_JOB_HANDLE]

    async def test_assign_failure_closes_job_and_child(self, monkeypatch: Any) -> None:
        fake = _FakeK32(fail_assign=True)
        monkeypatch.setattr(_win_job, "_k32", fake)
        assert assign_tree(7) is None
        assert fake.closed == [_PROC_HANDLE + 7, _JOB_HANDLE]

    async def test_no_kernel32_degrades_to_none(self, monkeypatch: Any) -> None:
        monkeypatch.setattr(_win_job, "_k32", None)
        assert assign_tree(1) is None
