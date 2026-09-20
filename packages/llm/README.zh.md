# llm

> 语言：简体中文 | [English](README.md)

## 目的

LLM 域:供应商目录、chat/stream/embedding 调用、用量计量、按价目表换算成本。

## 配置

llm.* 设置:默认 provider/model、采样、embedding 模型、价目表(llm.pricing)。

## 扩展点

新的供应商 = 目录中的一个预设;新的调用类型 = capabilities/ 下一个客户端模块加一个能力文件。

## 模型体验

工具:llm__complete / complete_stream / embed / get_usage_stats。agent 很少直接调用它们 —— 由 harness 传输层代劳。complete 以软失败返回已分类的错误(限流 / 认证 / 溢出)。

## 已知限制

仅在 chat 格式的供应商(OpenAI 兼容)上支持 embedding。

## 暂缓事项

按用途的供应商健康跟踪。
