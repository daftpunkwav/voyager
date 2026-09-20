# platform/actor — Actor 与认证

> 语言：简体中文 | [English](README.md)

- Actor 模型：`{ kind: user | agent | external, id, scopes[] }`（契约在 platform_contracts）；
- 本机认证：首次启动时生成本机秘密，用以签名/校验 HMAC 会话令牌；
- **agent 没有后门**：agent 持有自己的 actor 凭据，通过与用户相同的检查；
- 凭据传递：`ActorContext` 沿调用链流动；`restrict()` 只能收窄它，任何一步都不得提权。

---

## 用途

Actor 模型（user/agent/external/system + id + scopes）与本机令牌认证；ActorContext 沿调用链流动且只能被收窄。

## 配置

无（令牌文件路径为注入）。

## 扩展点

新增 actor kind = platform_contracts 中的一处契约变更，加上此处的检查。

## 已知限制

仅 HMAC 令牌（无刷新/轮换界面）。

## 暂缓事项

令牌吊销列表。
