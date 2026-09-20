# plugins — User plugins

One subdirectory per plugin, **declarative**: plugin.json manifest + skills/ + hooks/ +
mcp.json (external MCP server configuration). Plugins do not import platform implementations;
tools/skills/hooks must be approved by the user before they enter the system (per item or per package).
`_example/` is the minimal example.
