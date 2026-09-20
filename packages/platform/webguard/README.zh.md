# platform/webguard

> 语言：简体中文 | [English](README.md)

## 用途

共享的 URL 安全守卫：SSRF 策略、DNS 解析并固定（resolve-and-pin）、逐跳重定向检查。

## 配置

无（纯策略代码）。

## 扩展点

新守卫 = 多一个纯模块；使用方将 ValueError 翻译为自己的错误词汇。

## 模型体验

与模型无关的安全机制。

## 已知限制

fake-ip 网段（198.18.0.0/15）按策略放行（Clash 类代理）；未做固定的使用方仍存在 TOCTOU。

## 暂缓事项

为 agent web 工具提供可选的完全固定（pinning）辅助。
