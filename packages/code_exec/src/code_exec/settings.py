"""code-exec service settings: runtime images, resource limits,
network switch.

Language environments are data: adding a runtime only changes settings, not
code. Setting keys use the code_exec underscore form (naming-neutral; dotted
keys only allow underscores).
"""

from platform_settings import SettingDef, SettingType

_DEF_RUNTIMES = [
    {
        "id": "python",
        "name": "Python 3",
        "image": "python:3.11-slim",
        "file_ext": ".py",
        "cmd": ["python"],
    },
    {
        "id": "node",
        "name": "Node.js 20",
        "image": "node:20-slim",
        "file_ext": ".js",
        "cmd": ["node"],
    },
    {
        "id": "shell",
        "name": "Shell (bash)",
        "image": "bash:5.2",
        "file_ext": ".sh",
        "cmd": ["bash"],
    },
]

DEFS = [
    SettingDef(
        key="code_exec.runtimes",
        module="code_exec",
        type=SettingType.JSON,
        default=_DEF_RUNTIMES,
        description="Available runtime list (id/name/image/file_ext/cmd)",
    ),
    SettingDef(
        key="code_exec.timeout_seconds",
        module="code_exec",
        type=SettingType.INT,
        default=60,
        min=1,
        max=3600,
        description="Per-execution timeout (seconds)",
    ),
    SettingDef(
        key="code_exec.memory_mb",
        module="code_exec",
        type=SettingType.INT,
        default=512,
        min=64,
        max=8192,
        description="Container memory limit (MB)",
    ),
    SettingDef(
        key="code_exec.network",
        module="code_exec",
        type=SettingType.BOOL,
        default=False,
        description="Whether containers may reach the network by default (unless explicitly enabled)",
    ),
    SettingDef(
        key="code_exec.use_host",
        module="code_exec",
        type=SettingType.BOOL,
        default=True,
        description="Fall back to host process when docker is missing (dev/test only)",
    ),
]
