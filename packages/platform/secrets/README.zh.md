# platform/secrets — 密钥保管

> 语言：简体中文 | [English](README.md)

静态加密、按需下发，并在框架层对日志与事件载荷中的秘密做脱敏；
**secret 类设置的唯一写入路径是用户经本包写入**。BYOK：用户填入自己的
LLM key；没有 key 时 agent 降级。

---

## 用途

密钥保管：静态加密的 sqlite（SECRETS_ENCRYPTION_KEY），按键的 get/set/has/delete；密钥材料不可用时抛出 SecretUnavailableError。

## 配置

SECRETS_ENCRYPTION_KEY 环境变量（在装配根设置）。

## 扩展点

无可扩展之处——键按使用方划分命名空间（如 llm.provider.<id>.api_key）。

## 已知限制

单一机器级密钥；无按秘密的 ACL。

## 暂缓事项

密钥轮换工具。
