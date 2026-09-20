# plugins — 用户插件

> 语言：简体中文 | [English](README.md)

每个插件一个子目录，**声明式**：plugin.json 清单 + skills/ + hooks/ + mcp.json（外部 MCP 服务器配置）。插件不 import 平台实现；工具/技能/钩子必须经用户批准才能进入系统（逐项或逐包）。`_example/` 是最小示例。
