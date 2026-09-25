"""agent.mcp: service discovery (discovery) + external MCP connection
pool (pool/session).

pool.py: external MCP connection pool (validation/connection);
mount.py: turn remote tools into AgentTools in the root Toolbelt
(approval/mounting);
session.py: production MCP session paths (stdio subprocess and HTTP URL);
discovery.py: discover module cards from each service's service.json at
startup (read-only, no connections).

Domain tools (notes__* etc.) already go through the host.bridge
capability bridge; never ingest packages/*/mcp_server into the tool surface
via the MCP client.
"""

from agent.mcp.discovery import discover_services
from agent.mcp.pool import MCP_KEY, McpClientPool, validate_server_config
from agent.mcp.session import McpSession

__all__ = [
    "MCP_KEY",
    "McpClientPool",
    "McpSession",
    "discover_services",
    "validate_server_config",
]
