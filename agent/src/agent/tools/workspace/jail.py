"""Workspace jail: resolve agent-supplied paths into allowed roots.

Single enforcement point for the inner layer of the two-layer fs defense
(this module, then the PolicyEngine check in the toolbelt): relative paths
anchor at the first root, and the resolved path must land inside one of the
allowed roots. Read/write relaxation follows the same semantics as the
policy layer: read_roots open read tools only, write_roots open reads and
write/delete (tier judged by policy). The *_fn providers hot-read settings
and take priority over the frozen snapshots.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path


class Jail:
    """Path jail over workspace roots with optional extra roots."""

    def __init__(
        self,
        roots: list[str | Path],
        read_roots: list[str | Path] | None = None,
        write_roots: list[str | Path] | None = None,
        *,
        read_roots_fn: Callable[[], list[str | Path]] | None = None,
        write_roots_fn: Callable[[], list[str | Path]] | None = None,
    ) -> None:
        if not roots:
            raise ValueError("jail needs at least one root")
        self._roots = [Path(r).resolve() for r in roots]
        self._read_roots = read_roots
        self._write_roots = write_roots
        self._read_roots_fn = read_roots_fn
        self._write_roots_fn = write_roots_fn

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    def _extra(
        self,
        fallback: Iterable[str | Path] | None,
        fn: Callable[[], list[str | Path]] | None,
    ) -> list[Path]:
        raw = fn() if fn is not None else (fallback or ())
        return [Path(r).resolve() for r in raw]

    def resolve(
        self,
        path: str,
        *,
        allow_read_roots: bool = False,
        allow_write_roots: bool = False,
    ) -> Path:
        """Resolve an agent-supplied path; ValueError when outside all
        allowed roots (the caller surfaces it as a tool failure)."""
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._roots[0] / candidate
        resolved = candidate.resolve()
        allowed = self._roots
        if allow_read_roots:
            allowed = allowed + self._extra(self._read_roots, self._read_roots_fn)
        if allow_write_roots:
            allowed = allowed + self._extra(self._write_roots, self._write_roots_fn)
        if not any(resolved == r or r in resolved.parents for r in allowed):
            raise ValueError(f"路径在工作目录之外: {resolved}")
        return resolved

    def contains(
        self,
        path: str | Path,
        *,
        allow_read_roots: bool = True,
        allow_write_roots: bool = True,
    ) -> bool:
        """Whether a path lands inside the allowed roots.

        Callers pass candidate.resolve(): a workspace symlink pointing
        outside is therefore refused, matching resolve() exactly. Used to
        re-check directory-walk and glob hits that resolve() never saw.
        """
        resolved = Path(path).resolve()
        allowed = self._roots
        if allow_read_roots:
            allowed = allowed + self._extra(self._read_roots, self._read_roots_fn)
        if allow_write_roots:
            allowed = allowed + self._extra(self._write_roots, self._write_roots_fn)
        return any(resolved == r or r in resolved.parents for r in allowed)

    def display(self, path: Path) -> str:
        """Stable display form: relative to the first root when inside,
        absolute otherwise."""
        try:
            return path.resolve().relative_to(self._roots[0]).as_posix()
        except ValueError:
            return str(path)


__all__ = ["Jail"]
