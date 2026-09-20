# 双语文档

[English](README.md) | 中文

`docs/` 下每篇文档以英文与简体中文两种语言维护,两者权威等同。本页定义配对形态与一致性记录;写作规则见 [../AGENTS.zh.md](../AGENTS.zh.md)。

## 配对形态

一组配对是同目录下的三个同级文件:

- `foo.md` — 英文文档。
- `foo.zh.md` — 中文对应版,在 H1 之后立即回链(`[English](foo.md) | 中文`);英文侧对等(`English | [中文](foo.zh.md)`)。
- `foo.i18n.yaml` — 一致性记录:两侧最近一次确认一致时的 git blob 哈希。

```yaml
foo.md: 3f786850e387550fdab836ed7e6dc881de23001b
foo.zh.md: 89e6c98d92887913cadf06b2adb97f26cde4849b
```

## 结构镜像

标题深度与顺序、列表类型、有序列表起始、表格行列数、逐字代码块在配对两侧一一对应。双语文档之间的相对链接使用目标侧语言;指向源码的链接保留真实路径。

## 更新配对

变更修改任一侧时:

1. 同一变更内更新对应版,按已编辑侧的 diff 做最小修补 — 不整篇重译。
2. 重新记录两侧哈希:

```sh
git hash-object docs/subsystems/foo.md docs/subsystems/foo.zh.md
# 把两个哈希写入 docs/subsystems/foo.i18n.yaml
```

记录的哈希对与文件现状不符,即表示配对失同步,需按同样两步修复。

## 术语

全库保持术语稳定:capability → 能力,domain → 域,tool → 工具,setting → 设置(键),event → 事件,subagent → 子代理,turn/round → turn/轮,workspace → 工作区,persona → 人格,skill → 技能,memory → 记忆,checkpoint → 检查点,trajectory → 轨迹。英文更清晰时(如 `write_roots`、`parity`、`wiring`),两种语言都保留英文术语。
