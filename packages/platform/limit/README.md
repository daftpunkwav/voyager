# platform/limit — 限流与配额(骨架)

四层限流(§7.5):入口限流(gateway)/ 能力配额(capability 框架,已实现 CostQuota)/
agent 自律(policy 引擎)/ 服务背压(各服务队列)。

本包承接**入口限流**的共享机制(每 actor 每分钟请求数、SSE 连接数),gateway 落地时实现。
