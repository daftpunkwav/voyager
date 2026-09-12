# agent.clients — 外接 MCP server 连接

- `pool.py`:连接池。用户在设置页添加 stdio/URL 配置(`agent.mcp.servers`),
  连接并列出远端 tools;连接实现可注入,测试用 Fake。同一 server 的连接
  串行化(并发 preview 复用一条连接);收尾断开尽力而为并留日志。
- `mount.py`:把远端 tools 按 `mcp__<id>__<tool>` 挂进 Toolbelt;
  批准(整包/逐项)与移除卸载在此。批准只是进名册的门;调用走 app 维
  白名单(与桥工具同一套 `agent.app.allowed`)。
- `session.py`:MCP 会话产品路径(stdio 子进程 shell=False、HTTP POST
  JSON-RPC),最小握手 initialize → tools/list / tools/call。stdio 的
  请求-响应整段串行化(单消费者流,并发读会互相偷走响应行)。
- `discovery.py`:启动时按各服务 service.json 发现模块卡(只读卡,不连接)。

领域工具(notes__* 等)已走 host.bridge 的 capability 桥,
禁止再用 MCP client 把 services/*/mcp_server 灌进工具面。
