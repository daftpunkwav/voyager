# gateway

> 语言：简体中文 | [English](README.md)

## 目的

HTTP 载体:能力挂载、chat SSE、上传、活动流、健康检查、限流、安全响应头。

## 配置

gateway.* 设置:每分钟速率限制、SSE 连接上限。

## 扩展点

新的传输路由 = 本包下的一个 router 模块;业务逻辑留在各域。

## 模型体验

模型无关的传输;agent 经由桥访问能力,人经由 REST。

## 已知限制

仅单实例(限流器/SSE 状态存于内存)。

## 暂缓事项

WebSocket 传输。
