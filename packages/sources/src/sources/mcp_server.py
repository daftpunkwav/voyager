"""Registry -> MCP server over stdio; agents and external clients consume
sources capabilities through it.

Run: python -m sources.mcp_server (repo root; needs 'mcp>=1.0').
"""

from __future__ import annotations


def main():
    from platform_capability import build_server, secure_data_dir

    from .wiring import wire

    root = secure_data_dir("sources-mcp")
    w = wire(root, workspace=root / "data" / "workspace")
    return build_server(w.registry, name="sources")


if __name__ == "__main__":
    main()
