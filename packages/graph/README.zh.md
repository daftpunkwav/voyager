# graph

> 语言：简体中文 | [English](README.md)

## 目的

graph 域:从已导入的来源构建并查询知识图谱(节点/关系);包含代码与 L0 流水线,外加一个 AI 向导。

## 配置

graph.* 设置键(引擎选择、队列并发)。

## 扩展点

新的流水线 = pipelines/ 下一个目录(它们之间不得互相 import);引擎适配器位于 engines/。

## 模型体验

工具:graph__enqueue_index, graph__query_graph, graph__expand_neighbors, graph__find_path, graph__cancel_index, ... 任务为异步(task.* 事件);查询返回有界的子图。

## 已知限制

C 引擎为 vendored 且依赖具体平台;布局较为基础。

## 暂缓事项

无需全量重建索引的增量图谱更新。
