# browser

> 语言：简体中文 | [English](README.md)

## 目的

browser 域:把浏览器动作(导航/点击/输入/读取/截图)转发给外部浏览器 host。

## 配置

browser.* 设置键(host 端点)。

## 扩展点

新的动作 = capabilities.py 中一个转发到 host 协议的能力。

## 模型体验

工具(启用时):browser__navigate / click / type / read / screenshot。慢且有状态 —— 页面需要 JS 或交互时使用,其余情况优先 web_fetch。

## 已知限制

依赖外部浏览器 host;默认关闭。

## 暂缓事项

会话池化;多标签页记账。
