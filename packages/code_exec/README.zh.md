# code_exec

> 语言：简体中文 | [English](README.md)

## 目的

代码执行域:在各运行时环境(python/node/shell)中运行代码片段/文件,docker 优先,并提供显式的 host 回退。

## 配置

code_exec.* 设置:运行时表、超时、内存、网络模式、host 回退开关。

## 扩展点

新的运行时 = code_exec.runtimes 中的一项。

## 模型体验

工具(启用时):code_exec__run_snippet / run_file(异步 JobRef;结果经 task.* 事件返回)以及 list_runtimes。与 agent 的同步 run_shell 互补。

## 已知限制

默认关闭(docker 因环境而异);工件位于 workspace/sandbox 之下。

## 暂缓事项

按运行时的资源配额;输出流式传输。
