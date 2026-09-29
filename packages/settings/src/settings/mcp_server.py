"""Expose the settings capability registry as an MCP server over
stdio.

Agents and external clients consume settings capabilities through this
entry point. Run from the repository root:
python -m settings.mcp_server (requires pip install 'mcp>=1.0').
"""

from __future__ import annotations


def main():
    from platform_capability import build_server, secure_data_dir

    from .wiring import wire

    w = wire(secure_data_dir("settings-mcp"))
    return build_server(w.registry, name="settings")


if __name__ == "__main__":
    main()
