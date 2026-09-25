# agent

> 语言：简体中文 | [English](README.md)

## 用途

agent：事件循环、master 编排、子代理、上下文/记忆、policy、工具、技能、插件。

## 配置

`agent.*` 设置键（声明于 settings.py；其中包括 rounds / context / fs / network / llm / memory / skills / outreach / execution 等分组）。

## 扩展点

新工具 = tools/<group>/ 下的一个文件；新能力 = capabilities/<group>/ 下的一个文件（同名、同引擎 —— parity）；新模式 = engine/modes/ 下的一个文件。

## 模型体验

模型所交互的内容都在这里：工具描述、确认对话框、记忆、上下文预算。

## 已知限制

设计上即单进程、单用户。

## 暂缓事项

超出当前进程内实例树的多代理监督。
