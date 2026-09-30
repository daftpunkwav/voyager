"""Shared filesystem anchors for the source-checkout layout.

Several modules need repository-anchored default paths (repo-root
data/runtime, workspace, plugins/, the root .env). They used to hardcode
`Path(__file__).parents[4]` (or [3]/[5], depending on the file's depth),
so a layout change had to be replayed at every site. This module keeps one
depth assumption with the layout math written down once.
"""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Repository root (the directory holding packages/, agent/, apps/).

    Resolved from this file's own location
    (packages/platform/contracts/src/platform_contracts/paths.py), so every
    caller shares one depth assumption instead of scattering parents[N]
    magic numbers whose N silently depends on each file's depth.

    Limitation: source-checkout layout only (editable installs), the same
    accepted assumption as platform_secrets.key_material — a non-source
    install resolves a wrong root; every current caller only uses it for
    defaults in a local single-user deployment.
    """
    # paths.py -> platform_contracts -> src -> contracts -> platform -> packages -> repo
    return Path(__file__).resolve().parents[5]


__all__ = ["repo_root"]
