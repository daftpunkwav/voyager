"""Permission engine facade: hot-readable dimension snapshots dispatched to
the per-dimension decision functions (network / fs / app / shell, one file
each; the skill dimension is decided inline below).
Decisions are pure; the confirmation interaction lives in the invoke pipeline
(tools/core/invoke.py) — since the confirm channel retired, its one survivor
is the write_roots residual keyed by Decision.confirm_scope.

Resource counting (rounds/tokens/concurrency) is tracked at execution
points; the engine only provides the limits (ResourcePolicy).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from agent.policy.app import AppPolicy, decide_app
from agent.policy.decision import Decision
from agent.policy.fs import FsPolicy, decide_fs
from agent.policy.levels import Level
from agent.policy.network import NetworkPolicy, decide_network, narrow_network
from agent.policy.shell import ShellPolicy, decide_shell


@dataclass(frozen=True)
class ResourcePolicy:
    max_rounds: int = 20  # ReAct round limit
    max_tool_calls: int = 40
    max_subagents: int = 3
    daily_tokens: int = 0  # 0 = unlimited


@dataclass(frozen=True)
class Action:
    dimension: str  # network | fs | app | shell | skill | resource | none
    target: str = ""  # url / path / capability name / command
    write: bool = False
    irreversible: bool = False
    detail: str = ""


class PolicyEngine:
    """Network / filesystem / in-app / shell permission decisions."""

    def __init__(
        self,
        *,
        network: NetworkPolicy | None = None,
        fs: FsPolicy | None = None,
        app: AppPolicy | None = None,
        resource: ResourcePolicy | None = None,
        shell_level: Level = Level.L2_CONFIRM,
        shell: ShellPolicy | None = None,
        settings=None,  # optional settings handle (anything with get(key)); decisions hot-read it
    ) -> None:
        self.network = network or NetworkPolicy()
        self.fs = fs or FsPolicy()
        self.app = app or AppPolicy()
        self.resource = resource or ResourcePolicy()
        self.shell_level = shell_level
        # shell prefix rules default to the snapshot level; a bare shell_level
        # argument keeps working (BC) as ShellPolicy(level=shell_level)
        self.shell = shell or ShellPolicy(level=shell_level)
        self._settings = settings

    def decide(self, action: Action) -> Decision:
        handler = {
            "network": self._decide_network,
            "fs": self._decide_fs,
            "app": self._decide_app,
            "shell": self._decide_shell,
            "skill": self._decide_skill,
        }.get(action.dimension)
        if handler is None:
            # none/resource/unknown dimensions are intentionally allowed at L0;
            # log once so a dimension wiring slip does not disappear silently.
            logging.getLogger(__name__).info(
                "policy fallback: allowing unknown dimension %s for %s",
                action.dimension,
                action.target,
            )
            return Decision(allow=True)  # none/resource and the like: L0
        return handler(action)

    def _network_policy(self) -> NetworkPolicy:
        """The network policy for this decision: with a settings handle, hot-read the current
        values (settings changes take effect without restart); otherwise use the snapshot from
        construction (unit-test path)."""
        if self._settings is None:
            return self.network
        return NetworkPolicy(
            mode=self._settings.get("agent.network.mode"),
            domains=tuple(self._settings.get("agent.network.domains") or ()),
        )

    def _app_policy(self) -> AppPolicy:
        """The in-app whitelist for this decision: hot-read with a settings handle, else the
        construction snapshot. Invalid values (non-string lists) fall back to the snapshot
        wholesale, so a bad setting is never read as deny-all and left crippling the agent."""
        if self._settings is None:
            return self.app
        try:
            allowed_raw = self._settings.get("agent.app.allowed")
            denied_raw = self._settings.get("agent.app.denied")
            allowed = list(allowed_raw) if isinstance(allowed_raw, (list, tuple, set)) else None
            denied = list(denied_raw) if isinstance(denied_raw, (list, tuple, set)) else None
            if (
                allowed is None
                or denied is None
                or not all(isinstance(x, str) for x in allowed + denied)
            ):
                return self.app
            return AppPolicy(allowed=frozenset(allowed), denied=frozenset(denied))
        except Exception:  # noqa: BLE001  # on settings errors fall back to the snapshot
            return self.app

    def _fs_policy(self) -> FsPolicy:
        """The fs policy for this decision: with a settings handle, hot-read the additional
        read-only and read-write roots (settings changes take effect without restart); otherwise
        use the construction snapshot (unit-test path). roots (workspace) are not hot-read --
        workspace changes are an assembly-time concern. Invalid values (non-string lists) fall
        back to the snapshot wholesale."""
        if self._settings is None:
            return self.fs
        try:
            read_raw = self._settings.get("agent.fs.read_roots")
            write_raw = self._settings.get("agent.fs.write_roots")
            if read_raw is None and write_raw is None:
                return self.fs
            if read_raw is not None and (
                not isinstance(read_raw, (list, tuple, set))
                or not all(isinstance(x, str) for x in read_raw)
            ):
                return self.fs
            if write_raw is not None and (
                not isinstance(write_raw, (list, tuple, set))
                or not all(isinstance(x, str) for x in write_raw)
            ):
                return self.fs
            return FsPolicy(
                roots=self.fs.roots,
                read_roots=tuple(read_raw) if read_raw is not None else self.fs.read_roots,
                write_roots=tuple(write_raw) if write_raw is not None else self.fs.write_roots,
            )
        except Exception:  # noqa: BLE001  # on settings errors fall back to the snapshot
            return self.fs

    def _decide_network(self, action: Action) -> Decision:
        return decide_network(self._network_policy(), action)

    def _decide_fs(self, action: Action) -> Decision:
        return decide_fs(self._fs_policy(), action)

    def _decide_app(self, action: Action) -> Decision:
        return decide_app(self._app_policy(), action)

    def _decide_shell(self, action: Action) -> Decision:
        return decide_shell(self._fs_policy(), self.shell, action)

    @staticmethod
    def _decide_skill(action: Action) -> Decision:
        """Skill-library dimension: writes land in the resident skill index
        the next turn (the same subtree file/shell tools must not touch), so
        writes and irreversible ops are reported at L2 — a level invoke.py no
        longer confirms (confirm retired; the skills subtree itself stays
        write-protected via the fs/shell guards). Reads stay silent."""
        if action.write or action.irreversible:
            return Decision(True, Level.L2_CONFIRM, "Skill library writes require confirmation")
        return Decision(allow=True)


__all__ = [
    "Action",
    "AppPolicy",
    "Decision",
    "FsPolicy",
    "NetworkPolicy",
    "PolicyEngine",
    "ResourcePolicy",
    "ShellPolicy",
    "narrow_network",
]
