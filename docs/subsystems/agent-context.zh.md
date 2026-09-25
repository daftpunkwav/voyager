# Agent 上下文工程

[English](agent-context.md) | 中文

模型可见提示如何组装、预算、裁剪、压缩,以及缓存健康如何监视。

源码:`agent/src/agent/context/`

## 提示组装

`builder.py` — `ContextBuilder.system(...)` 以固定、字节稳定的顺序组装系统提示(对前缀缓存友好):

1. `【全局规则】` — `prompts/definitions/common.toml` (`common.global_rules`)
2. 作用域规则 — `workspace/AGENTS.md`
3. `【用户准则】` — 设置 `agent.conduct`
4. 人格 system prompt
5. `【人格准则】` — `agent.guidelines[persona]`
6. `【风格】` — `agent.style` / 按人格 `agent.style.overrides`
7. `【可用 skill】` — 只放名称 + 一行简介(正文按需加载)

随后是稳定在先、易变在后的尾部:用户画像、近期记忆卡、任务书(goal/constraints/done_when)、相关度召回节(`read_policy.py`)、进行中子代理摘要、用户当前页面上下文、计划评审态(`plan_gate.py`)、MCP 指引。

每个 turn 由 `engine/turn.py:run_turn` 重建系统提示;历史由 `ContextBudget` 约束。

## 预算

`budgets.py` — `ContextBudget` dataclass;`budget_from_settings(settings, model_name)` 解析按模型窗口档案(`agent.context.model_profiles`)与可用窗口。代表性默认值:`HISTORY_MAX=60` 跨 turn 条目(成对丢弃)、`COMPRESS_BUDGET=6000`、`auto_compact_at=75`(可用窗口百分比)、`compact_target` 未设时取 40%、记忆/召回/技能/摘要/画像/任务/页面的字符上限。全部由 `agent.context.*` 设置支撑([config-catalog.zh.md](../catalog/config-catalog.zh.md))。

`runtime/tokenizer.py` — CJK 感知的 token 估算(位于 runtime 层,由 context 与 runtime 共用)。

## 治理器

`governor.py` — `ContextGovernor.enforce()` 是每 turn 的权威:

1. `prune()`(`prune.py`)— 确定性滚动 microcompact:旧的超大工具结果收缩为 `…[已压缩]` 标记,受 `agent.context.prune_protect_tokens`(默认 4000)保护、`prune_min_tokens` 约束。
2. `compact()`(`editor.py` `compact_transcript`)— 仍超阈值时:LLM 规划的转录重构(规划路径为主,确定性回退),`CompactionBackoff`(`MAX_REMAINING_RATIO = 0.8`)抑制重复低产出的规划。摘要以 `[历史压缩]` 标记的 user 消息回到历史。

`compressor.py` — `compress(messages, budget)`:确定性截断旧工具结果,然后按对形态淘汰最旧条目(assistant+tool 一次运行不拆散),始终保留最近 8 条。

## 缓存监视

`prefix_watch.py` — `PrefixWatch`:系统提示与工具名册的 turn 级哈希,基于供应商上报 `cached_tokens` 的轮级缓存健康(热后转冷 = 断裂;未命中阈值 1000 token),以及逐消息哈希差分定位。发现项记录到日志 `agent.context.prefix`。

## 按需加载与页面上下文

`loader.py` — `OnDemandLoader` 只在构建器索要时供给 `skill_text` 与 `recall` 载荷。`pages.py` — `PageContextRegistry` 持有前端上报的当前页面(能力 `report_page_context`);构建器按字符上限(`agent.context.page_chars`)把它渲染进提示。
