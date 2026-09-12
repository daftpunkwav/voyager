# plugins — User plugins

One subdirectory per plugin, **declarative** (§9.13): plugin.json manifest + skills/ + hooks/ +
mcp.json (external MCP server configuration). Plugins do not import platform implementations;
tools/skills/hooks must be approved by the user before they enter the system (granularity optional: per item / per package, decision §15).
`_example/` is the minimal example.
