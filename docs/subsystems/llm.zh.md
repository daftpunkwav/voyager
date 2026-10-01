# LLM 域

[English](llm.md) | 中文

`llm` 域拥有组合系统中全部模型交互:供应商管理、补全与流式、用量计量、定价、嵌入。agent 从不 import 本包;host 通过晚加绑调用把 agent 的聊天传输接到这里([host.zh.md](host.zh.md))。

源码:`packages/llm/src/llm/` — 端口 8070,默认启用,存储 `data/runtime/llm/llm.db`。

## 能力

`Registry("llm")`,`capabilities/` 下每个能力一个模块:

- 供应商管理:`list_builtin_providers`、`list_providers`、`get_provider_defaults`、`add_provider`、`update_provider`、`remove_provider`、`set_api_key`
- 模型:`list_models`、`list_remote_models`、`test_connection`
- 推理:`complete`(cost 10)、`complete_stream`(流式)
- 遥测:`get_usage_stats`
- 嵌入:`embed`

## 客户端

`client.py` 使用原生 httpx(不用 litellm)。一个客户端覆盖三种 wire 格式,按供应商的 `api_format` 选择:

- `chat` — OpenAI `/chat/completions`
- `anthropic` — `/v1/messages`
- `responses` — OpenAI `/v1/responses`(解析器在 `wire_responses.py`)

工具以中立格式(`[{"name", "description", "schema"}]`)传输,再按 wire 格式翻译。上游错误被分类(限流 / 认证 / 上下文溢出 / 瞬态),有界重试 2 次、退避 0.5 秒,遵循封顶 5 秒的 `Retry-After`。

出站加固:`add_provider`/`update_provider` 校验 `base_url`(http(s) 且含主机名;公网端点必须 https;私网/loopback 目标仅 USER 可配,并记为该供应商行的 `private_endpoint`)。每次请求前由 `net_pin.pinned_ip` 解析供应商主机一次——USER 授权的私网端点照常解析(本地 Ollama 不受影响)——并用 `pinned_request` 把请求构建到已校验的 IP 上(保留原 Host 头与 TLS SNI),封死解析与连接之间的重绑定窗口。解析失败映射为 `LLM.UNAVAILABLE`;未授权供应商解析到私网映射为 `LLM.FORBIDDEN`,且解析到的内网 IP 不进入错误消息。

## 存储

`store.py` — `ProviderStore`(SQLite `llm.db`):`providers`(base_url、api_format、models、enabled、custom、private_endpoint)与 `usage`(ts、provider_id、model、caller、input/output/cached/reasoning/cache-write tokens、ok)。API key 绝不存这里 — 存入 `SecretStore`(`platform_secrets`)。`catalog.py` 持有 `BUILTIN_PROVIDERS` 预设(如 `openai`、`openai-responses`、`anthropic`、`deepseek`、`moonshot`)。

## 用量与定价

`complete` 对每次调用计量,包括失败(`ok=0`)。`get_usage_stats` 从 `usage` 表聚合。`pricing.py` 只在读取侧把 token 换算为成本,依据 `llm.pricing` 设置(`{"<模型或前缀>": {"input", "output"}}`,美元/每百万 token,最长前缀匹配);未定价模型不产生成本。`configured_reasoning_effort(provider, model)` 将 `llm.reasoning_effort` 与所服务模型配置的思考档位做解析(`resolve_reasoning_effort`;设置页的模型配置是唯一来源):空值跟随模型的 `thinking_default`,`off` 表示显式关闭,覆盖值必须是该模型 `thinking_variants` 之一(陈旧值回落到默认);没有档位列表的模型保留旧版规范名 `low`/`medium`/`high` 直通。`reasoning_fields` 在 chat/responses 格式上把解析值原样透传;anthropic 格式把规范名映射为固定 thinking budget,非规范档位按其在模型档位列表中的位置推导预算(首位=最低,末位=最高;不在列表中的名字在该格式上保持不注入)。

两个推理能力都在回答文本之外返回归一化的响应元数据:`finish_reason`(按 wire 格式 — chat `finish_reason`、anthropic `stop_reason`、responses `status`)、`request_id`(取自 `x-request-id` / `request-id` / `anthropic-request-id` / `cf-ray`)、`response_id`(responses 格式)、`service_tier`、`stop_sequence`、`created`;usage 细分出各格式的 `reasoning_tokens` 与 `cache_write_tokens`。供应商拒绝响应携带 `request_id` 与被拒请求原文的 dump 路径:dump 经环境变量 `LLM_DEBUG_DUMP_DIR` 显式开启,绝不写入请求头,文件以 0o600 创建(Unix),且目录有界——每次 dump 之后只保留最新 200 份。anthropic wire 上,流式解析器把 `message_delta.usage` 视为权威累计用量(非零字段覆盖 `message_start` 快照 — 现行契约;兼容端点在 `message_start` 只报 0 占位,同样适用)。`complete` 的 `max_tokens` 入参以 `0` 表示"自动":此时上限取自 `llm.max_output_tokens`。

## 设置

`llm.default_provider`、`llm.default_model`、`llm.temperature`、`llm.max_output_tokens`、`llm.embedding_model`、`llm.reasoning_effort`、`llm.pricing`。

## 消费方

- host LLM 路由(`host/llm_routing.py`)— agent 聊天、arbiter、蒸馏、上下文规划用途按 `agent.llm.routing` / `agent.llm.overrides` 在此解析。无 provider 可解析或整条路由链都在线上失败时,路由器返回降级回复(`degraded=True`)而非抛错;其文本由 `degraded_error_text`(`agent/src/agent/llm.py`)构造——complete 与 stream 两条路径的唯一构造点,把 llm 域的错误串只包一层,耗尽链条的变体还会注明尝试次数。
- host 嵌入适配器(`host/embedder_adapter.py`)— agent 记忆向量召回经 `call_sync("llm", "embed", ...)`。
- 前端设置页 — 供应商/模型管理与用量面板经 REST 直接调用 `llm` 能力。
