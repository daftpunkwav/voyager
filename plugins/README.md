# plugins — 用户插件

每个插件一个子目录,**声明式**(§9.13):plugin.json 清单 + skills/ + hooks/ +
mcp.json(外接 MCP server 配置)。插件不 import 平台实现;
tools/skills/hooks 进入系统前必须经用户批准(粒度可选:逐项/整包,决策 §15)。
`_example/` 为最小示例。
