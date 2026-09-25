# Config catalog

English | [中文](config-catalog.zh.md)

Every registered settings key, grouped by owner. Keys register through `platform_settings.SettingDef` at wire time; the framework validates and persists values in `settings.db`. Sources are authoritative for current defaults; where the default is a module constant, the constant name appears below.

## Agent (`agent/src/agent/settings.py`)

### Execution and rounds

| Key | Type | Default |
|---|---|---|
| `agent.rounds.max` | INT | 20 |
| `agent.rounds.tool_max` | INT | 40 |
| `agent.rounds.max_tokens` | INT | 0 (unlimited) |
| `agent.execution.tool_deadline_s` | FLOAT | 90 |
| `agent.execution.round_deadline_s` | FLOAT | 240 |
| `agent.arbiter.mode` | CHOICE | `queue` |
| `agent.direct_chat` | BOOL | false |
| `agent.resource.daily_tokens` | INT | 0 (unlimited) |

### Permissions and policy

| Key | Type | Default |
|---|---|---|
| `agent.permissions` | JSON | module default (`PERMISSIONS_DEFAULT`) |
| `agent.fs.read_roots` | JSON | `[]` |
| `agent.fs.write_roots` | JSON | `[]` |
| `agent.network.mode` | CHOICE | `whitelist` |
| `agent.network.domains` | JSON | `["github.com", "arxiv.org"]` |
| `agent.app.allowed` | JSON | `["*"]` |
| `agent.app.denied` | JSON | `[]` |

### LLM transport and routing

| Key | Type | Default |
|---|---|---|
| `agent.llm.base_url` | STR | `""` (standalone transport) |
| `agent.llm.api_key` | STR | `""` |
| `agent.llm.model` | STR | `""` |
| `agent.llm.timeout_s` | INT | 120 |
| `agent.llm.routing` | JSON | `{}` |
| `agent.llm.overrides` | JSON | `{}` |
| `agent.pricing.overrides` | JSON | `{}` |

### Context

| Key | Type | Default |
|---|---|---|
| `agent.context.window_tokens` | INT | 200000 |
| `agent.context.max_output_tokens` | INT | 64000 |
| `agent.context.model_profiles` | JSON | `{}` |
| `agent.context.auto_compact_at` | INT | 75 |
| `agent.context.compact_target` | INT | 0 (40% of window) |
| `agent.context.compress_budget` | INT | 6000 |
| `agent.context.history_max` | INT | 60 |
| `agent.context.tool_result_max` | INT | 8000 |
| `agent.context.tool_result_max_lines` | INT | 2000 |
| `agent.context.prune_protect_tokens` | INT | 4000 |
| `agent.context.prune_min_tokens` | INT | 2000 |
| `agent.context.skill_max` | INT | constant `SKILL_MAX` |
| `agent.context.skill_chars` | INT | constant `SKILL_CHARS` |
| `agent.context.mcp_chars` | INT | constant `MCP_CHARS` |
| `agent.context.digest_chars` | INT | constant `DIGEST_CHARS` |
| `agent.context.task_chars` | INT | constant `TASK_CHARS` |
| `agent.context.page_chars` | INT | constant `PAGE_CHARS` |

### Memory and skills

| Key | Type | Default |
|---|---|---|
| `agent.memory.retention_days` | INT | 90 |
| `agent.memory.distill_interval` | INT | 10 |
| `agent.memory.context_cards` | INT | 5 |
| `agent.memory.context_card_chars` | INT | 600 |
| `agent.memory.recall_facts` | INT | 4 |
| `agent.memory.recall_chars` | INT | 600 |
| `agent.memory.profile_chars` | INT | constant `PROFILE_CHARS` |
| `agent.skills.organize_every` | INT | 30 |

### Subagents, triggers, outreach

| Key | Type | Default |
|---|---|---|
| `agent.subagents.max_concurrent` | INT | 3 |
| `agent.subagents.max_depth` | INT | 3 |
| `agent.triggers.cooldown_s` | INT | 300 |
| `agent.outreach.enabled` | BOOL | true |
| `agent.outreach.daily_max` | INT | 3 |
| `agent.outreach.session_max` | INT | 1 |
| `agent.outreach.cooldown_minutes` | INT | 120 |
| `agent.outreach.quiet_hours` | STR | `23:00-08:00` |

### Conduct, workspace, MCP, plugins, observability, evaluation

| Key | Type | Default |
|---|---|---|
| `agent.conduct` | STR | `""` |
| `agent.style` | STR | `热心` |
| `agent.guidelines` | JSON | `{}` |
| `agent.style.overrides` | JSON | `{}` |
| `agent.workspace.dir` | STR | `data/workspace` |
| `agent.clients.servers` | JSON | `[]` |
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

## Domain settings

| Owner | Key | Type | Default | Declared in |
|---|---|---|---|---|
| gateway | `gateway.chat.history_page_size` | INT | 200 | `packages/gateway/src/gateway/settings.py` |
| gateway | `gateway.rate_limit.per_minute` | INT | 600 | same |
| gateway | `gateway.sse.max_connections` | INT | 8 | same |
| graph | `graph.engine.mode` | CHOICE | `auto` | `packages/graph/src/graph/settings.py` |
| graph | `graph.engine.c_url` | STR | constant `DEFAULT_C_URL` | same |
| graph | `graph.index.concurrency` | INT | 1 | same |
| graph | `graph.index.max_attempts` | INT | 3 | same |
| graph | `graph.query.default_limit` | INT | 200 | same |
| llm | `llm.default_provider` | STR | `""` | `packages/llm/src/llm/settings.py` |
| llm | `llm.default_model` | STR | `""` | same |
| llm | `llm.temperature` | FLOAT | 0.7 | same |
| llm | `llm.max_output_tokens` | INT | 4096 | same |
| llm | `llm.embedding_model` | STR | `""` | same |
| llm | `llm.reasoning_effort` | STR | `""` | same |
| llm | `llm.pricing` | JSON | `{}` | same |
| notes | `notes.sort.default` | CHOICE | `updated` | `packages/notes/src/notes/settings.py` |
| notes | `notes.list.page_size` | INT | 100 | same |
| notes | `notes.editor.autosave_s` | INT | 5 | same |
| notes | `notes.trash.retention_days` | INT | 30 | same |
| notes | `notes.history.per_note` | INT | 20 | same |
| notes | `notes.export.dir` | STR | `workspace/notes-export` | same |
| notes | `notes.assets.max_mb` | INT | 20 | same |
| notes | `notes.ui.*` (12 keys) | mixed | see source | same |
| office | `office.export.dir` | STR | `workspace/exports/` | `packages/office/src/office/settings.py` |
| sources | `sources.sort.default` | CHOICE | `added` | `packages/sources/src/sources/settings.py` |
| sources | `sources.import.clone` | BOOL | true | same |
| sources | `sources.doc.max_file_mb` | INT | 200 | same |
| settings domain | `appearance.theme` | CHOICE | `system` | `packages/settings/src/settings/settings.py` |
| settings domain | `appearance.locale` | CHOICE | `zh-CN` | same |
| settings domain | `appearance.font_scale` | FLOAT | 1.0 | same |
| settings domain | `appearance.code_font` | STR | `JetBrains Mono` | same |
| settings domain | `privacy.activity_report` | BOOL | true | same |
| browser | `browser.headless` | BOOL | true | `packages/browser/src/browser/settings.py` |
| browser | `browser.allowed_domains` | JSON | `[]` | same |
| code_exec | `code_exec.runtimes` | JSON | `_DEF_RUNTIMES` | `packages/code_exec/src/code_exec/settings.py` |
| code_exec | `code_exec.timeout_seconds` | INT | 60 | same |
| code_exec | `code_exec.memory_mb` | INT | 512 | same |
| code_exec | `code_exec.network` | BOOL | false | same |
| code_exec | `code_exec.use_host` | BOOL | true | same |
| host | `host.domains.enabled` | JSON | `[]` | `packages/host/src/host/plan.py` |
| _template | `template.worker.concurrency` | INT | 1 | `packages/_template/…/settings.py` |
