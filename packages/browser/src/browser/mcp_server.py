"""Expose the browser capability registry as an MCP server over
stdio.

Agents and external clients consume browser capabilities through this
entry point. Run from the repository root:
python -m browser.mcp_server (requires pip install 'mcp>=1.0').
"""

from __future__ import annotations


def main():
    import tempfile
    from pathlib import Path

    from platform_capability import build_server

    from .wiring import wire

    w = wire(
        Path(tempfile.gettempdir()) / "browser-mcp",
        workspace=Path(tempfile.gettempdir()) / "browser-workspace",
    )
    return build_server(w.registry, name="browser")


if __name__ == "__main__":
    main()
