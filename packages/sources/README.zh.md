# sources

> 语言：简体中文 | [English](README.md)

## 目的

sources 域:从三个模块 —— repo(git)、doc(文件)、web(网页)—— 导入并检索素材。

## 配置

sources.* 设置键(github token、索引器并发)。

## 扩展点

新的导入器 = modules/ 下一个带自有 capabilities.py 的模块;共享的 URL 安全来自 platform_webguard。

## 模型体验

工具:sources__import_repo / save_url / search_documents / list_*。导入返回 id;检索返回带评分的命中。在 graph 索引之前使用。

## 已知限制

Web 导入只走 SSRF 安全的抓取(无 JS 渲染);文档抽取覆盖常见文本格式。

## 暂缓事项

更多抽取器(pdf 表格);增量重建索引的调度。
