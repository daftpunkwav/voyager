# 配置目录

[English](config-catalog.md) | 中文

全部已注册的设置键,按属主分组。键在接线时经 `platform_settings.SettingDef` 注册;框架校验并把值持久化到 `settings.db`。当前默认值以源码为权威;默认值为模块常量处,下表标注常量名。

## Agent(`agent/src/agent/settings.py`)

### 执行与轮次

| 键 | 类型 | 默认 |
|---|---|---|
| `agent.rounds.max` | INT | 20 |
| `agent.rounds.tool_max` | INT | 40 |
| `agent.rounds.max_tokens` | INT | 0(不限) |
| `agent.execution.tool_deadline_s` | FLOAT | 90 |
| `agent.execution.round_deadline_s` | FLOAT | 240 |
| `agent.arbiter.mode` | CHOICE | `queue` |
| `agent.direct_chat` | BOOL | false |
| `agent.resource.daily_tokens` | INT | 0(不限) |

### 权限与策略

| 键 | 类型 | 默认 |
|---|---|---|
| `agent.permissions` | JSON | 模块默认(`PERMISSIONS_DEFAULT`) |
| `agent.fs.read_roots` | JSON | `[]` |
| `agent.fs.write_roots` | JSON | `[]` |
| `agent.network.mode` | CHOICE | `whitelist` |
| `agent.network.domains` | JSON | `["github.com", "arxiv.org"]` |
| `agent.app.allowed` | JSON | `["*"]` |
| `agent.app.denied` | JSON | `[]` |

### LLM 传输与路由

| 键 | 类型 | 默认 |
|---|---|---|
| `agent.llm.base_url` | STR | `""`(独立传输) |
| `agent.llm.api_key` | STR | `""` |
| `agent.llm.model` | STR | `""` |
| `agent.llm.timeout_s` | INT | 120 |
| `agent.llm.routing` | JSON | `{}` |
| `agent.llm.overrides` | JSON | `{}` |
| `agent.pricing.overrides` | JSON | `{}` |

### 上下文

| 键 | 类型 | 默认 |
|---|---|---|
| `agent.context.window_tokens` | INT | 200000 |
| `agent.context.max_output_tokens` | INT | 64000 |
| `agent.context.model_profiles` | JSON | `{}` |
| `agent.context.auto_compact_at` | INT | 75 |
| `agent.context.compact_target` | INT | 0(窗口的 40%) |
| `agent.context.compress_budget` | INT | 6000 |
| `agent.context.history_max` | INT | 60 |
| `agent.context.tool_result_max` | INT | 8000 |
| `agent.context.tool_result_max_lines` | INT | 2000 |
| `agent.context.prune_protect_tokens` | INT | 4000 |
| `agent.context.prune_min_tokens` | INT | 2000 |
| `agent.context.skill_max` | INT | 常量 `SKILL_MAX` |
| `agent.context.skill_chars` | INT | 常量 `SKILL_CHARS` |
| `agent.context.mcp_chars` | INT | 常量 `MCP_CHARS` |
| `agent.context.digest_chars` | INT | 常量 `DIGEST_CHARS` |
| `agent.context.task_chars` | INT | 常量 `TASK_CHARS` |
| `agent.context.page_chars` | INT | 常量 `PAGE_CHARS` |

### 记忆与技能

| 键 | 类型 | 默认 |
|---|---|---|
| `agent.memory.retention_days` | INT | 90 |
| `agent.memory.distill_interval` | INT | 10 |
| `agent.memory.context_cards` | INT | 5 |
| `agent.memory.context_card_chars` | INT | 600 |
| `agent.memory.recall_facts` | INT | 4 |
| `agent.memory.recall_chars` | INT | 600 |
| `agent.memory.profile_chars` | INT | 常量 `PROFILE_CHARS` |
| `agent.skills.organize_every` | INT | 30 |

### 子代理、触发、外联

| 键 | 类型 | 默认 |
|---|---|---|
| `agent.subagents.max_concurrent` | INT | 3 |
| `agent.subagents.max_depth` | INT | 3 |
| `agent.triggers.cooldown_s` | INT | 300 |
| `agent.outreach.enabled` | BOOL | true |
| `agent.outreach.daily_max` | INT | 3 |
| `agent.outreach.session_max` | INT | 1 |
| `agent.outreach.cooldown_minutes` | INT | 120 |
| `agent.outreach.quiet_hours` | STR | `23:00-08:00` |

### 准则、工作区、MCP、插件、可观测、评估

| 键 | 类型 | 默认 |
|---|---|---|
| `agent.conduct` | STR | `""` |
| `agent.style` | STR | `热心` |
| `agent.guidelines` | JSON | `{}` |
| `agent.style.overrides` | JSON | `{}` |
| `agent.workspace.dir` | STR | `data/workspace` |
| `agent.mcp.servers` | JSON | `[]` |
| `agent.mcp.refresh_seconds` | INT | 300 |
| `agent.mcp.instructions` | BOOL | true |
| `agent.plugins.approved` | JSON | `[]` |
| `agent.plugins.approvals` | JSON | `{}` |
| `agent.observability.exporter` | CHOICE | `memory` |
| `agent.observability.otlp_endpoint` | STR | `http://localhost:4318/v1/traces` |
| `agent.observability.langfuse_host` | STR | `https://cloud.langfuse.com` |
| `agent.observability.langfuse_public_key` | STR | `""` |
| `agent.observability.langfuse_secret_key` | STR | `""` |
| `agent.evaluation.enabled` | BOOL | true |
| `agent.evaluation.mode` | CHOICE | `heuristic` |
| `agent.evaluation.min_score_threshold` | FLOAT | 0.6 |

## 域设置

| 属主 | 键 | 类型 | 默认 | 声明位置 |
|---|---|---|---|---|
| gateway | `gateway.chat.history_page_size` | INT | 200 | `packages/gateway/src/gateway/settings.py` |
| gateway | `gateway.rate_limit.per_minute` | INT | 600 | 同上 |
| gateway | `gateway.sse.max_connections` | INT | 8 | 同上 |
| graph | `graph.engine.mode` | CHOICE | `auto` | `packages/graph/src/graph/settings.py` |
| graph | `graph.engine.c_url` | STR | 常量 `DEFAULT_C_URL` | 同上 |
| graph | `graph.index.concurrency` | INT | 1 | 同上 |
| graph | `graph.index.max_attempts` | INT | 3 | 同上 |
| graph | `graph.query.default_limit` | INT | 200 | 同上 |
| llm | `llm.default_provider` | STR | `""` | `packages/llm/src/llm/settings.py` |
| llm | `llm.default_model` | STR | `""` | 同上 |
| llm | `llm.temperature` | FLOAT | 0.7 | 同上 |
| llm | `llm.max_output_tokens` | INT | 4096 | 同上 |
| llm | `llm.embedding_model` | STR | `""` | 同上 |
| llm | `llm.reasoning_effort` | STR | `""` | 同上 |
| llm | `llm.pricing` | JSON | `{}` | 同上 |
| notes | `notes.sort.default` | CHOICE | `updated` | `packages/notes/src/notes/settings.py` |
| notes | `notes.list.page_size` | INT | 100 | 同上 |
| notes | `notes.editor.autosave_s` | INT | 5 | 同上 |
| notes | `notes.trash.retention_days` | INT | 30 | 同上 |
| notes | `notes.history.per_note` | INT | 20 | 同上 |
| notes | `notes.export.dir` | STR | `workspace/notes-export` | 同上 |
| notes | `notes.assets.max_mb` | INT | 20 | 同上 |
| notes | `notes.ui.*`(12 键) | 混合 | 见源码 | 同上 |
| office | `office.export.dir` | STR | `workspace/exports/` | `packages/office/src/office/settings.py` |
| sources | `sources.sort.default` | CHOICE | `added` | `packages/sources/src/sources/settings.py` |
| sources | `sources.import.clone` | BOOL | true | 同上 |
| sources | `sources.doc.max_file_mb` | INT | 200 | 同上 |
| settings 域 | `appearance.theme` | CHOICE | `system` | `packages/settings/src/settings/settings.py` |
| settings 域 | `appearance.locale` | CHOICE | `zh-CN` | 同上 |
| settings 域 | `appearance.font_scale` | FLOAT | 1.0 | 同上 |
| settings 域 | `appearance.code_font` | STR | `JetBrains Mono` | 同上 |
| settings 域 | `privacy.activity_report` | BOOL | true | 同上 |
| browser | `browser.headless` | BOOL | true | `packages/browser/src/browser/settings.py` |
| browser | `browser.allowed_domains` | JSON | `[]` | 同上 |
| code_exec | `code_exec.runtimes` | JSON | `_DEF_RUNTIMES` | `packages/code_exec/src/code_exec/settings.py` |
| code_exec | `code_exec.timeout_seconds` | INT | 60 | 同上 |
| code_exec | `code_exec.memory_mb` | INT | 512 | 同上 |
| code_exec | `code_exec.network` | BOOL | false | 同上 |
| code_exec | `code_exec.use_host` | BOOL | true | 同上 |
| host | `host.domains.enabled` | JSON | `[]` | `packages/host/src/host/plan.py` |
| _template | `template.worker.concurrency` | INT | 1 | `packages/_template/…/settings.py` |
