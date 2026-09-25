# Agent 记忆、技能、人格

[English](agent-memory.md) | 中文

源码:`agent/src/agent/memory/`、`skills/`、`personas/`。

## 记忆库

`memory/__init__.py` — `Memory(root, embedder=None)` 拥有 `data/runtime/agent/memory/` 下四个库:

- `ProfileMemory`(`profile.db`)— 键/值用户画像。
- `EpisodicMemory`(`episodic.db`)— 逐工具调用轨迹;工具带的情景记录器写入每次已执行调用。
- `SemanticMemory`(`semantic.db`)— 主语/关系/宾语事实。
- `WorkingMemory` — 内存中的近期 user/assistant 轮次。

`recall(query, limit=8)` 聚合 profile/episodic/semantic 的词法命中加可选向量通道(`memory/vector.py`,使用注入的 embedder;嵌入不可用时降级为 `EmbeddingUnavailable` 标记)。`purge(retention_days)` 遵循 `agent.memory.retention_days`(0 = agent 自管);`clear(zone)` 清空指定区。

## 蒸馏

`distill.py` — `Distiller.maybe_distill()` 每 `agent.memory.distill_interval` 个 turn 触发:一次 LLM 调用产出严格 JSON,落入 profile/semantic 写入。蒸馏只读工作记忆,不读全量日志。

## 读策略

`read_policy.py` — `render_relevant_recall` 是系统提示中的常驻相关度层:召回事实按内容寻址渲染(相同事实 → 相同字节),保持提示前缀缓存稳定。

## 聊天会话

`sessions/store.py` — `SessionStore`(`data/runtime/agent/sessions.db`):`SessionMeta`/`SessionSnapshot`、活动会话指针、既单行迁移。`SessionManager`(`sessions/manager.py`)在其上叠加身份、生命周期、会话锁与原始轮记录器接线。

## 技能

`skills/loader.py` — `SkillLoader(roots)` 扫描各根下的 `<name>/SKILL.md`。`index()` 只返回名称 + 首行简介(≤120 字符);`full_text(name)` 按需加载(不可读 → `KeyError`)。`add_root`/`remove_root` 支撑插件热加载/卸载。内置根:`agent/src/agent/skills/builtin` 与 `workspace/skills`。

`skills/organizer.py` — `SkillOrganizer` 在情景记忆中检视重复的连续工具调用序列(≥2 个不同工具),按 `agent.skills.organize_every` 节奏发出非阻塞 `skill.proposed` 事件;保存经 `skill` 工具的 propose 动作。

## 人格

`personas/base.py` — `Persona(key, display_name, style, system_prompt, default_mode="react", tool_allow=None)`(frozen)。`personas/__init__.py` 在 import 时加载全部 `personas/definitions/*.toml`;键重复即响亮失败。内置职责键:`orchestrator`、`recon`、`explainer`、`organizer`、`graph_guide`(旧别名经 `ALIASES` 折叠;未知或用户自定义名经 `resolve_persona` 返回 None)。
