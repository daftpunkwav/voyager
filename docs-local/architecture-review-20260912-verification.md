# 审查报告复核记录 — architecture-review-20260912-glm-5.3-flash.md

> **复核日期**:2026-09-13
> **复核基线**:main @ `eec4506`(feat/agent-system-phase15-22 已 fast-forward 合并)
> **方法**:逐项对照 file:line 与代码行为核实 12 项发现(F-101~F-112),再对属实项实施修复。修复后门禁:gate:py 全绿(ruff / import-linter / mypy / pytest 1565 / 依赖图);gate:web 前四步全绿(tsc / eslint / vitest 54 文件 / i18n),format:check 红为既有 CRLF 环境问题(268 文件,数量与既有记录一致)。

## 一、逐项裁定

| 发现 | 裁定 | 依据与处置 |
|---|---|---|
| F-101 单进程聚合 | **属实** | `dev.py:33` 单 uvicorn 属实。**暂缓**:修复为部署形态级变更(lifespan 逐域降级 / 多进程实测),报告自身亦列入阶段 2 尾/阶段 3,且与装配根现行 fail-fast 语义存在设计张力,需单独拍板 |
| F-102 PluginManager 双职责 | **属实,已修** | 方法表逐条核实(675 行)。安装器六方法迁 `plugins/installer.py`(258 行),manager 保留薄委托,能力面与测试零改动。manager 675→517(装载+审批+查询单一变更理由;报告建议的 <500 未强凑) |
| F-103 events.db 无保留 | **属实,已修** | log.py 全文件确无 purge;每条 `agent.delta` 均经 `publish→to_thread(append)` 落盘。新增 `EventLog(retention=Retention(types,max_age_s,sweep_every))` + 公开 `purge()`;策略由调用方注入(平台不硬编码业务事件名),两个装配根共用 `agent.build.EVENTS_RETENTION`(agent.delta 保留 24h,消息级事件永不清理) |
| F-104 驱逐不删 checkpoint | **属实,已修** | `_trim_terminal_instances` 仅 pop 内存。现驱逐时同步 `checkpoints.delete(run_id)`;终态 checkpoint 本就不在 `list_alive`(按 status.alive 过滤),删除无行为回归 |
| F-105 前端硬编码后端状态前缀 | **核心机制失实** | 全仓(grep -E + git log -S)核实:`[状态]`/`执行·`/`意图识别:`/`推理中…轮` 等前缀**只存在于前端历史提交**(RepoPilot 前端原样迁移),voyager 后端/prompt 从不产出。报告的"改后端一行文案前端静默失效"不成立;§17"重命名攻击实锤"不成立。真实残余:①该正则是对 LLM 思考流文本的启发式过滤,存在误滤真思考的理论面(产品行为,未动);②防御规则为遗留死规则。已在 `isStatusLine` 补澄清注释(无品牌词,过 naming-neutral 门禁)。**不建议**按报告方向做结构化事件字段改造(解决不存在的问题) |
| F-106 llm_http 无重试 | **属实,已修** | 镜像 packages/llm 语义:2 次有界重试、0.5s 指数退避、Retry-After 上限 5s;`_NO_RETRY_NET`(Read/Write/Pool timeout)连接建立后不重试;流式仅重试"未产出任何 delta 前"的发起阶段。8 个新测试(含 429 hint、穷尽降级、流式 502 重试、非瞬态不重试) |
| F-107 前端 5 文件超 500 行 | **属实(行数全核实),暂缓拆分** | chatStore 681/681 等数字全部准确。但报告自身仅 chatStore 为"拆分信号成立",其余 4 个为"信号";chatStore 三切片是 M 级前端重构,涉多会话 lane 归档逻辑,vitest 不足以兜底,应配合 preview 真人式验证单独做 |
| F-108 4 个占位目录 | **属实但已缓解** | 四份 README 均已标注 "(skeleton)" 并写明实现落点(audit 甚至写明现实现位于 capability 包)。报告要求的"显式声明预留"已满足,"无契约约束"对零代码目录无实害。**无需改动** |
| F-109 SessionStore 线程纪律 | **属实,已修** | `check_same_thread=False` 属实;全部调用面核实均在 loop 线程(async 工具处理器不经 to_thread)。docstring 显式声明纪律与缓解来源(MasterSessions.lock_for) |
| F-110 settings 同名异物 | **属实,已修** | 两 README 增加互注 blockquote |
| F-111 SSE 容量未验证 | **属实(自认 UNVERIFIED),暂缓** | 需压测基建,非代码修复 |
| F-112 instance↔turn 回边 | **属实但系有意设计** | turn.py:1 docstring 明言 "`inst` is duck-typed;importing the class here would cycle",instance→turn 运行时边 + turn→instance 仅 TYPE_CHECKING 注解,运行图无环。上提共享类型需搬核心状态机类或造 Protocol(漂移风险),收益仅静态工具计数。**不改,维持文档化现状** |

## 二、顺带发现与修复(非报告项)

- **web_search/web_fetch 测试非密闭(存量)**:测试只打桩 HTTP transport,未打桩 `resolve_public`,真实 DNS 泄漏进测试。本机解析器对 `html.duckduckgo.com` 返回被 webguard 判为内网的 IPv6(`2001::c73b:95e6`),工具在请求前正确拒绝,5 个 web_search 用例在零代码改动下失败(eec4506 上复现,非本次修复引入)。已为两组测试补 `resolve_public` 打桩,门禁恢复全绿——即报告 F-003"结构性解决"方向的真实收尾。
- 报告事实引用质量高:抽核的全部 file:line 与 wc -l 数字均准确(含 manager 455-629、spawn 256-269、agentThinking 20-28、sessions.py:369 等)。

## 三、修复提交清单(merge 后 main)

| commit | 内容 |
|---|---|
| `b50760c` | F-104:终态实例驱逐同步删 checkpoint(+测试) |
| `c6b283c` | F-106:独立 LLM 通道有界瞬态重试(+8 测试) |
| `a81c9f3` | F-102:安装器拆出 PluginInstaller(manager 675→517 / installer 258) |
| `cee2090` | F-103:EventLog 保留策略 + 两装配根接线(+3 测试) |
| `ecc7673` | F-109/F-110 注释与 README 互注;F-105 复核澄清注释 |
| `4e4ea4a` / `3190491` | 测试插入位移修复 / 漏提交的打桩迁移 + 注释去品牌词 |
| `f6185f7` | 存量:web_fetch/web_search 测试补 DNS 守卫打桩(密闭化) |
| `ab2c196` | 自审加固:驱逐删 checkpoint 改 best-effort(Windows 锁文件不再污染 start/cancel 结果)、重试仅消耗于 TransportError 瞬态族、append 计数移入锁内 + rowcount 归一化 |

## 四、留给后续决策

1. **F-101 部署形态**(唯一"严重"项):是否按 minimal(lifespan 逐域隔离降级)或 recommended(code_exec 先行多进程实测)推进,涉及装配根 fail-fast 语义调整,建议单独立任务书。
2. **F-107 chatStore 三切片**:M 级前端重构,建议配合 preview 真人式验证(四页 e2e 流程)单独安排。
3. **F-111 SSE 容量压测**:需要压测基建/脚本。
4. agentThinking 遗留正则的取舍(删遗留死规则 vs 保留为启发式)属产品行为决策,未动。
