"""Registry -> MCP server (stdio). Agents / external clients consume
code-exec capabilities through it.

Run: python -m code_exec.mcp_server (from the repo root; requires
pip install 'mcp>=1.0')
"""

from __future__ import annotations


def main():
    from platform_capability import build_server, secure_data_dir

    from .wiring import wire

    w = wire(
        secure_data_dir("code-exec-mcp"),
        workspace=secure_data_dir("code-exec-workspace"),
    )
    return build_server(w.registry, name="code-exec")


if __name__ == "__main__":
    main()
