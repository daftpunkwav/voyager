# agent.clients — External MCP server connections

- `pool.py`: connection pool. The user adds stdio/URL configs on the settings
  page (`agent.mcp.servers`), and the pool connects and lists remote tools;
  the connection implementation is injectable, with Fakes for tests.
  Connections to the same server are serialized (concurrent previews reuse a
  single connection); teardown disconnects best-effort and leaves logs.
- `mount.py`: mounts remote tools into the Toolbelt as `mcp__<id>__<tool>`;
  approval (whole package / per item) and removal/unmount live here.
  Approval is only the gate onto the roster; calls go through the app-level
  allowlist (the same `agent.app.allowed` as bridge tools).
- `session.py`: the production path for MCP sessions (stdio subprocess with
  shell=False, HTTP POST JSON-RPC), with a minimal handshake of initialize →
  tools/list / tools/call. stdio request-response exchanges are serialized as
  a whole (single-consumer stream; concurrent reads would steal each other's
  response lines).
- `discovery.py`: at startup, discovers module cards from each service's
  service.json (read-only cards, no connection).

Domain tools (notes__* etc.) already go through the host.bridge capability
bridge; feeding services/*/mcp_server into the tool surface via an MCP client
is forbidden.
