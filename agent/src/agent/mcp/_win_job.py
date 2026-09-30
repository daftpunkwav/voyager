"""Windows Job Object wrapper: process-tree reclamation for stdio MCP servers.

A stdio MCP server is often a launcher shim (`npx ...`, `uvx ...`, a `.cmd`
resolved through cmd.exe) whose real server runs as a grandchild. Terminating
the direct child alone leaves those grandchildren alive holding the inherited
pipe handles: our stdout never sees EOF and the orphan runs until reboot.
Assigning the spawned process to a Job Object with
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE makes the whole tree die when this
handle closes - covering the async close path, the loop-less sync shutdown,
and a crash/exit of this process (the OS closes the handle for us).

Assignment failure (non-Windows, a job edge case, restricted token) degrades
to None and the caller keeps its previous direct-child-only behavior.

The module imports on every platform (structs are plain ctypes; the kernel32
binding is built only on win32), so the caller needs no platform branch.
ctypes.WinDLL is resolved via getattr because the attribute only exists on
Windows (typeshed gates it on sys.platform, which breaks typecheck on Linux).
"""

from __future__ import annotations

import ctypes
import sys

_WINDOWS = sys.platform == "win32"

#: JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE - every process in the job is
#: terminated when the last job handle closes.
_KILL_ON_JOB_CLOSE = 0x00002000
#: JobObjectExtendedLimitInformation information class.
_JOBOBJECT_EXTENDED_LIMIT_INFO = 9
#: Access rights AssignProcessToJobObject requires on the child handle.
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001


class _BasicLimitInfo(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),  # ULONG_PTR
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class _ExtendedLimitInfo(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInfo),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


# Kernel32 binding: None off Windows. A module-level indirection so tests can
# drive the failure/success branches with a fake on any platform.
_k32: ctypes.LibraryLoader | None = None
if _WINDOWS:  # pragma: no cover - the binding needs a real Windows DLL
    _windll = getattr(ctypes, "WinDLL", None)
    if _windll is not None:
        _k32 = _windll("kernel32", use_last_error=True)
        _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        _k32.CreateJobObjectW.restype = ctypes.c_void_p
        _k32.SetInformationJobObject.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint32,
        ]
        _k32.SetInformationJobObject.restype = ctypes.c_int
        _k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        _k32.OpenProcess.restype = ctypes.c_void_p
        _k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        _k32.AssignProcessToJobObject.restype = ctypes.c_int
        _k32.CloseHandle.argtypes = [ctypes.c_void_p]
        _k32.CloseHandle.restype = ctypes.c_int


class ProcessTreeJob:
    """Owns one Job Object handle; close() terminates every member process.

    Idempotent: the second close is a no-op. A handle that is never closed is
    still safe - it is released at process exit, and the kill-on-close limit
    reaps the tree then.
    """

    def __init__(self, handle: int) -> None:
        assert _k32 is not None
        self._k32 = _k32
        self._handle = handle

    def close(self) -> None:
        """Close the job handle; members still alive are terminated."""
        handle, self._handle = self._handle, 0
        if handle:
            self._k32.CloseHandle(handle)


def assign_tree(pid: int) -> ProcessTreeJob | None:
    """Put `pid` into a kill-on-close job; None when unavailable or the
    assignment fails (the caller keeps direct-child-only termination)."""
    if _k32 is None:
        return None
    job = _k32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _ExtendedLimitInfo()
    info.BasicLimitInformation.LimitFlags = _KILL_ON_JOB_CLOSE
    if not _k32.SetInformationJobObject(
        job, _JOBOBJECT_EXTENDED_LIMIT_INFO, ctypes.byref(info), ctypes.sizeof(info)
    ):
        _k32.CloseHandle(job)
        return None
    proc = _k32.OpenProcess(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE, False, pid)
    if not proc:
        _k32.CloseHandle(job)
        return None
    assigned = _k32.AssignProcessToJobObject(job, proc)
    _k32.CloseHandle(proc)
    if not assigned:
        _k32.CloseHandle(job)
        return None
    return ProcessTreeJob(job)
