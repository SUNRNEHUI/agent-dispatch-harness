# Agent Reliability Harness

简体中文 | [English](README.md)

Agent Reliability Harness，曾使用 Agent Dispatch Harness 和 Multi-Agent Dispatcher 作为项目名，是面向 AI 编码代理的 skill，用于把明确的多智能体请求路由到最合适的执行模式。它避免小任务过度调度，并为长任务、高风险任务、可续跑任务和需要证据验收的任务提供持久化 harness。

当前版本：**v7.4.0** · 2026-07-18

---

## 概览

多智能体执行只在任务存在清晰的独立责任边界，或需要持久化协同时才有明显价值。本 skill 将“用户授权多智能体”与“实际启动多智能体”分开处理：用户可以请求多智能体工作，但主代理仍需要判断调度是否真的能提升结果质量。

主代理始终负责：

- 选择执行模式
- 定义目标、非目标、责任边界和验证要求
- 在有必要时把边界清晰的任务分配给子代理
- 合并结果并处理冲突
- 在声明完成前验证验收证据

子代理只负责边界明确的执行、调研、审查或评估任务。最终验收责任仍由主代理承担。

---

## 核心能力

- **模式选择：** 在创建 worker 或 artifact 之前，先选择 Direct、Lite 或 Full。
- **跨运行时模型路由：** 保持可移植 profile，同时分别封装 Codex/Grok 模型映射和真实回退。
- **选择性调度：** 只有在任务具备清晰责任边界时才分配子代理。
- **持久化状态：** 为长任务或可续跑任务保存 spec、进度、报告、状态和验收记录。
- **自动续接：** 新 Codex 或 Grok session 可从项目根自动发现、恢复、验证并原子接管唯一 active Full run。
- **运行时 TDD 证据：** 用 wrapper-generated trace 和可选文件系统 mtime 校验区分 strict TDD、test-first evidence、substitute verification 和 not applicable。
- **证据化验收：** 用测试、构建输出、日志、浏览器检查、截图、CI、readback 或 evaluator 报告支持完成结论。
- **运行时适配：** 将同一套协议映射到 Codex、Claude Code 或类似编码代理环境。
- **干净打包：** 生成 runtime-only 安装包，避免把仓库文档、本地缓存、生成工作区或私有配置复制到运行目录。

---

## 执行模式

| 模式 | 适用场景 | 行为 |
| --- | --- | --- |
| **Direct** | 任务较小、局部、顺序性强，或一个代理可以更高效完成。 | 不启动子代理，不创建编排 artifact。主代理直接执行并验证。 |
| **Lite** | 任务有少量可拆分部分，但不需要完整持久化 harness。 | 主代理使用简短计划、明确 owner、紧凑报告和针对性验证。 |
| **Full** | 任务较长、高风险、可续跑、需要并行、需要 evaluator，或适合 worktree 隔离。 | 主代理运行完整 harness，包括 capability 记录、状态文件、验收清单、trace、报告和验证 gate。 |

明确的多智能体请求代表授权进行模式选择，不代表必须启动多个 worker。
快捷触发词只启动密度路由，不强制进入 Full，也不强制调度多 agent。

---

## 适用场景

当用户明确要求以下能力时使用本 skill：

- 输入“你是主 agent”或“写一个 harness”以启动密度路由
- “写一个 harness 来解决这个问题”
- 多智能体 / 多 Agent
- sub-agent / 子 agent
- 代理委托
- 并行 agent
- DAG 调度
- 基于 worktree 的并行执行
- 分头处理 / 分别派 / 拆给不同 agent
- 需要可续跑或证据验收的长任务协同

不要仅仅因为任务较大就使用本 skill。如果用户没有授权多智能体执行，应继续使用普通单代理工作流；当多智能体确实能降低风险时，可以简要提出建议。

---

## 运行流程

```text
Context Intake
-> Mode Selection: Direct / Lite / Full
-> Execute Selected Mode
   Direct: 实现、验证、汇报
   Lite: 协调边界清晰的任务片段、验证、汇报
   Full: capability gate、acceptance registry、state machine、trace、evaluator
-> Merge / Handoff
```

主代理应始终选择能够保证质量和验证的最轻模式。

---

## Full Harness 协议

Full 模式用于需要强协同控制的任务。

### 1. Mode Selection Gate

主代理记录选择 Direct、Lite 或 Full 的原因。Full 模式通常由以下因素触发：独立责任面、长任务或可续跑范围、较高验证风险、evaluator 价值、隔离和回滚价值。

### 2. Capability Gate

分配任务前，主代理记录当前运行时真实可用的能力：

- 真实子代理或委托机制
- 文件系统写入权限
- shell 和 sandbox 限制
- worktree 支持
- 浏览器或 UI 验证能力
- 可承载协议规则的 instruction 文件或 hook
- 外部服务、凭据和网络假设

如果某项能力不可用，主代理必须选择回退路径，例如顺序执行、缩小范围、请求决策或进入停止状态。

### 3. State Machine

Full 模式使用明确状态推进：

```text
INTAKE -> GATED -> SPECIFIED -> DISPATCHED -> REPORTED -> EVALUATING -> ACCEPTED -> HANDED_OFF
```

停止状态同样是一等状态：

```text
BLOCKED -> NEEDS_DECISION -> FAILED
```

每次状态转换都应留下简短 trace，记录原因、owner、证据路径和下一个状态。

### 4. Acceptance Registry

验收标准以结构化记录保存。每条记录应包含：

- 验收标准
- owner
- 所需证据
- 状态：`pending`、`pass`、`fail`、`blocked` 或 `scoped_out`
- 证据路径或命令结果摘要

只要仍有必需验收项未验证，主代理就不能声明任务完成。

### 5. Budget Circuit Breaker

每个阶段应设置预算边界，包括时间、上下文、工具调用、重试、成本和外部副作用。当阶段超出预算时，主代理记录停止原因，并决定继续、拆分、缩小范围或请求决策。

### 6. Trace

Trace 记录续跑和审计所需的最小证据：

- capability gate 结果
- 状态转换
- worker 报告路径
- evaluator 结果
- 预算停止或重试原因
- 最终 acceptance registry

聊天记录不应被视为持久化任务状态。

### 7. 跨运行时续接

替代运行时从项目根开始，不依赖 artifact 路径或旧聊天：

```bash
python3 <skill-dir>/scripts/harnessctl.py resume . \
  --runtime grok --actor-id <unique-session-id> \
  --takeover-reason "previous Codex session interrupted"
```

`resume` 只接受唯一 active Full run；它先恢复未完成事务并验证完整 artifact，再在锁
内转移 owner，返回 required reads、active tasks、blockers、明确 next action、pending
verification、owner epoch 和工作树 drift。之后所有写命令都必须携带该 actor ID 和
epoch，旧 session 会 fail closed。

每个已验证边界后、可能中断前都应 checkpoint。源运行时可正常退出时使用 `handoff`；
突然中断时由接管方记录 takeover reason。该协议迁移的是持久化可观察状态，不是隐藏
思维、provider session 内部状态、secret 或正在进行的外部副作用。Harness 不接收额度
回调；所谓自动接管，是替代运行时启动后第一步执行 `resume`。

---

## 安装

克隆仓库：

```bash
git clone https://github.com/SUNRNEHUI/agent-reliability-harness.git
cd agent-reliability-harness
```

生成干净的 runtime 包：

```bash
python3 scripts/sync_version.py
python3 scripts/package_skill.py --verify-source
python3 scripts/package_skill.py --output /tmp/agent-reliability-harness-runtime --force
```

安装到 Codex：

```bash
mkdir -p ~/.codex/skills/agent-reliability-harness
rsync -a --delete /tmp/agent-reliability-harness-runtime/ ~/.codex/skills/agent-reliability-harness/
python3 scripts/package_skill.py --check ~/.codex/skills/agent-reliability-harness
```

runtime 包只包含 skill 运行时需要的文件。

---

## 从旧名称迁移

早期版本曾使用 Agent Dispatch Harness 作为公开项目和 runtime 名称，更早版本使用 `multi-agent-dispatcher`，一些本地安装也使用过 `multi-agent-orchestrator`。新的安装和公开传播应统一使用 `agent-reliability-harness`。

升级已有本地安装时，先安装新的 runtime 目录；如果旧目录仍存在且不再需要，可以删除：

```bash
rm -rf ~/.codex/skills/agent-dispatch-harness ~/.codex/skills/multi-agent-dispatcher ~/.codex/skills/multi-agent-orchestrator
```

这样可以避免同一套工作流以多个 skill 名称重复出现。

---

## Runtime 包内容

runtime 包包含：

- `VERSION`
- `SKILL.md`
- `master-prompt.md`
- `sub-prompt.md`
- `agents/openai.yaml`
- `adapters/`
- `references/`
  - `references/state-memory-boundary.md`
  - `references/model-routing.md`
- `templates/`
- `scripts/init_run.py`
- `scripts/harness_test_run.py`
- `scripts/status.py`
- `scripts/tdd_gate_check.py`
- `scripts/validate_report.py`
- `templates/lite_plan.md`
- `templates/lite_review.md`
- `templates/tdd_trace.jsonl`

权威文件清单以 `scripts/package_skill.py:RUNTIME_FILES` 为准；本节只概括 runtime 类别。

runtime 包会排除：

- `README.md`
- `README.zh-CN.md`
- `scripts/sync_version.py`
- `scripts/package_skill.py`
- `.git`
- 生成的 workspace artifact
- 本地 memory 文件
- session 日志
- 缓存和字节码
- 私有配置
- 凭据或 API key

---

## 使用示例

明确的多智能体请求：

```text
这个项目有前端、后端和测试三块。请在有价值的地方使用多个 agent，并提供验证证据。
```

带有多智能体措辞的小任务：

```text
如果需要可以用多智能体，帮我修正这个错别字。
```

预期行为：主代理应选择 Direct 模式，因为调度开销没有必要。

需要持久化协同的长任务：

```text
重构 checkout，更新 API contract，迁移测试，并验证 UI 流程。请使用子 agent，并让任务可以续跑。
```

预期行为：主代理根据风险、可用工具和验证要求选择 Lite 或 Full 模式。

---

## Artifact 初始化

Full 模式可以初始化持久化运行目录：

```bash
python3 scripts/init_run.py \
  --project-root /path/to/project \
  --title "Checkout Refactor" \
  --agents frontend,backend,tests
```

生成目录示例：

```text
/path/to/project/workspace/checkout-refactor/
├── acceptance_registry.json
├── capability_snapshot.md
├── task_spec.md
├── progress.md
├── run_state.json
├── trace.jsonl
├── tdd_trace.jsonl
├── evaluator_report.md
└── tasks/
    ├── 1.1-frontend.md
    ├── 1.2-backend.md
    └── 1.3-tests.md
```

---

## 报告校验

在使用报告结论前，可以先校验报告结构：

```bash
python3 scripts/validate_report.py <artifact-dir>/1.1-frontend-report.md --type subagent
```

支持的 artifact 类型：

- `spec`
- `progress`
- `subagent`
- `evaluator`

如果 `acceptance_registry.json` 或 `run_state.json` 与被校验 artifact 位于同一目录，校验器也会检查这些协议文件。

对于 TDD 敏感任务，可以校验专用 TDD trace：

```bash
python3 scripts/tdd_gate_check.py <artifact-dir>/tdd_trace.jsonl
```

该 checker 会校验 strict TDD 的时间顺序，接受已记录的 test-first gap evidence，并拒绝缺少替代验证理由的 substitute gate。

在可用时，建议通过测试包装器运行验证命令，让 trace 事件由运行时命令包装器生成，而不是由 agent 手写：

```bash
python3 scripts/harness_test_run.py \
  --trace <artifact-dir>/tdd_trace.jsonl \
  --task-id 1.1 \
  --gate-mode strict_tdd \
  --phase RED \
  --run-state <artifact-dir>/run_state.json \
  -- pytest path/to/test.py
```

对于 strict TDD 循环，可以使用 `tdd_gate_check.py --source-path <file>` 为当前循环改动的源文件增加文件系统 mtime 校验。

对于 CI 或发布 gate，可以要求 run 达到 high completion confidence：

```bash
python3 scripts/status.py <artifact-dir>/run_state.json --require-high-confidence
```

---

## 仓库结构

```text
agent-reliability-harness/
├── SKILL.md
├── README.md
├── README.zh-CN.md
├── adapters/
├── agents/
├── references/
├── scripts/
├── templates/
├── master-prompt.md
└── sub-prompt.md
```

详细协议材料位于 `references/`，运行时适配说明位于 `adapters/`。

---

## 运行时适配

协议本身不绑定特定运行时。适配文档说明如何在不同代理环境中落地：

- [Codex adapter](adapters/codex.md)
- [Grok adapter](adapters/grok.md)
- [Claude Code adapter](adapters/claude-code.md)
- [Harness protocol reference](references/harness-protocol.md)

适配文档不改变协议，只把同一组 gate、artifact、证据规则和回退行为映射到可用的运行时控制能力上。

---

## 与 Superpowers 的关系

本项目是独立实现，不依赖 Superpowers 运行。

本项目在设计上参考了 [obra/superpowers](https://github.com/obra/superpowers) 中的部分工程实践。Superpowers 是 Jesse Vincent 创建的软件开发方法体系。Agent Reliability Harness 借鉴的方向包括 test-first evidence、fresh-context sub-agents、review gates、worktree isolation 和 verification before completion。

本项目不复制 Superpowers 的 skill 正文，也不要求安装 Superpowers 插件。二者关系如下：

```text
agent-reliability-harness = 路由与 harness 权威
Superpowers-style methods = 可选的工程支持方法
```

模式选择始终先执行。只有当支持方法适合当前执行模式时，才会使用这些方法。

---

## 版本历史

### v7.4.0

- 新增唯一 active run 自动发现、事务恢复、跨运行时 owner 原子转移、完整 resume packet、显式 checkpoint/handoff 命令和旧 Full artifact 自动升级。
- 新增 actor+epoch fencing、歧义/损坏 fail-closed、工作树内容 drift 检测和 continuation 状态输出。
- 将既有 v7.3 Grok 模型路由和证据 refresh 命令带回源码，并对齐 Codex/Grok/universal adapter 与 runtime 包内容。

### v7.3.0

- 新增封装的 Grok 模型 profile、确定性的 `--runtime grok` 路由、Grok adapter 和可选低成本模型配置，不虚构本地不存在的默认模型。
- 新增 `task-refresh` 和 `acceptance-refresh`，用于按路径事务化替换过期 artifact receipt。

### v7.2.0

- 为 state/UI/async/concurrency 任务增加 Production State Witness 契约，要求记录真实 source locator、可达的 failing/fixed/preserved truth-table 行、Observed before/Expected after，以及独立审查入口。
- 将 witness 接入运行时门禁：stateful artifact 未通过 witness 校验时不能 seal、dispatch、validate 或进入 protected acceptance；独立 review 证据必须达到配置的 policy/flow/user-visible 层级。
- 新增 `witness-set`、sealed witness digest、sealed-baseline dispatch 检查、对抗式压力测试和 source/install package 漂移检查。

### v7.0.0

- 将项目和 runtime skill 正式更名为 Agent Reliability Harness。
- 围绕策略驱动、按比例执行和基于证据验收的定位，重写公开 README 并同步 runtime metadata。

### v5.11.0

- 对照 `Cjbuilds/Codex-Orchestration`，记录吸收的薄路由思路，以及明确取消或不引入的高开销 bridge 和 ceremony。
- 保持当前父任务模型为唯一 root orchestrator，让显式 `no subagents` 指令拥有最高优先级，并收紧真实模型路由状态的表达。
- 新增 `scripts/status.py --require-high-confidence`，供 CI 或发布 gate 使用；默认人读状态输出保持不变。
- 将默认对齐提问收敛到不可逆或影响验收的决策；普通歧义改为说明可回滚假设后继续执行。

### v5.10.0

- 新增面向 GPT-5.6 的 Codex 路由策略：在运行时支持显式控制时，简单子 agent 默认使用 Luna/low，中等任务升级 Terra，高风险审查使用 Sol。
- 新增 worker 数量、嵌套深度、task-local context、紧凑报告和模型覆盖不可用时的回退规则。
- 将 Superpowers 风格方法改为按风险触发的可选方法，不再默认套用整套 ceremony。
- 新增模型路由参考、回归用例和 runtime 打包覆盖，同时不引入 GPT-5.6 专属 API 字段。

### v5.9.0

- 新增按模式成比例执行的 Completion Confidence Loop，在最终交付前把完成声明映射到最新证据。
- 扩展 Verification 和 Evaluator 指导，要求暴露缺失检查、过期证据、stub、TODO、mock 和未验证关键路径。
- 增强 `scripts/status.py`，输出任务完成度、验收汇总、证据缺口、置信度档位和下一步验证建议。
- 在 progress ledger 和 Lite plan 模板中增加轻量的 confidence 与 evidence gap 提示。
- 保持执行模式按需收敛：Direct 仍不创建 artifact，Lite 仍保持紧凑，Full 仍用于高风险或可续跑任务的持久化协议。
- 未新增 artifact 类型。

### v5.8.0

- 新增 `VERSION` 和 `scripts/sync_version.py`，让当前版本引用可以从单一来源检查或更新。
- 为 runtime 包新增 `scripts/package_skill.py --verify-source` 和 `--check <install-dir>` 检查。
- 通过 `templates/lite_plan.md`、`templates/lite_review.md` 和 `init_run.py --mode lite` 增加 Lite Orchestration artifact。
- 保持 `progress.md` 轻量，并新增 `scripts/status.py` 从 `run_state.json` 生成单屏状态摘要。
- 为 `lite_plan`、`lite_review` 和 Lite `run_state.json` 增加 validator 支持，并新增 runtime 行为测试。
- 本版本不加入自动 mode-router evaluation；`references/eval_cases.md` 仍作为人读回归集合。

### v5.7.0

- 为 Full Harness run 新增明确的 State / Memory 边界。
- 明确 `task_spec.md` 是本地人读计划/spec，`run_state.json` 是机器可读实时状态。
- 新增 `state_layers`，区分 Working State、Session State、Execution Log 和 Memory Boundary。
- 新增 `references/state-memory-boundary.md`，并纳入 runtime 打包。
- 更新校验逻辑，要求 `run_state.json` 包含核心 `state_layers` 结构。

### v5.6.0

- 将公开项目和运行时 skill 从 Multi-Agent Dispatcher 重命名为 Agent Dispatch Harness。
- 更新仓库 URL、安装路径、runtime metadata 和中英文公开文档。
- 将 TDD 命令包装器重命名为 `scripts/harness_test_run.py`，并更新 trace `source` 字段。
- 增加旧本地安装名 `multi-agent-dispatcher` 和 `multi-agent-orchestrator` 的迁移说明。
- 保留 Direct、Lite、Full 三种执行模式，Full Harness 仍作为高级持久化执行协议。

### v5.5.0

- 新增 wrapper-generated TDD trace 支持，用于运行验证命令并写入 TDD trace；当前入口为 `scripts/harness_test_run.py`。
- 扩展 `scripts/tdd_gate_check.py`，支持 strict TDD 循环的可选 `--source-path` mtime 校验。
- 在 run-state 模板和初始化输出中新增 `tdd_current_cycle_context`。
- 明确普通 worker 应优先使用 wrapper-generated trace evidence，而不是手写 TDD trace。
- 在 Bugfix Lane 和 Feature-Spec Lane 中加入 retry、checkpoint 和 rollback 规则，同时不允许在主工作区默认自动执行 `git reset --hard`。

### v5.4.0

- 新增 Bugfix Lane 和 Feature-Spec Lane，让开发流程按任务类型分流。
- 新增 `templates/tdd_trace.jsonl` 和 `scripts/tdd_gate_check.py`，用于运行时中立的 TDD 时间顺序校验。
- 更新 run 初始化和 runtime 打包流程，确保 TDD trace artifact 和 checker 脚本被包含。
- 收紧 sub-agent 和 evaluator 模板，要求记录 trace path、chronology summary、first production edit 和 unverified critical path。
- 扩展 eval cases，覆盖 code-before-RED、passing-test-as-RED、shell-bypass、UI-only-unit-test、self-report-only 和 missing no-test-reason 等失败模式。
- 新增 `.gitignore`，避免生成的 workspace、worktree 和 Python cache 文件污染版本库。

### v5.3.0

- 新增两层测试模型：`Test-First Evidence Gate` 和 `Strict TDD Gate`。
- 新增 `references/tdd-gates.md`，说明 RED/GREEN、替代验证和主代理验收规则。
- 在 sub-agent report 中新增必填的 `Test-First Or Substitute Verification` 字段。
- 在协议 JSON 记录中新增 `verification_gate`。
- 更新校验脚本，避免 sub-agent report 和协议记录完全绕过 testing gate 结构。

### v5.2.2

- 将英文和中文 README 重写为正式的公开项目文档。
- 明确项目定位、执行模式、安装流程、runtime 包边界和 Superpowers 借鉴声明。
- 未改变运行协议。

### v5.2.1

- 新增中英文公开文档。
- 明确声明对 Superpowers 相关工程方法的借鉴关系。
- 新增 `scripts/package_skill.py`，用于生成干净的 runtime-only 安装包。
- 在公开 README 中整理 Direct、Lite 和 Full 三种执行模式。
- 扩展 eval cases，覆盖 TDD 证据、审查分离、Superpowers 关系和干净分享包。

### v5.0.1

- 在 capability check 和 DAG 创建前新增 right-sizing gate。
- 明确多智能体措辞只代表授权评估，不代表自动调度。
- 增加小任务跳过 worker、worktree 和 artifact 的指导。

### v5.0.0

- 将项目从流程说明升级为由主代理执行的 harness 协议。
- 新增 capability snapshot、`run_state.json`、`acceptance_registry.json` 和 `trace.jsonl`。
- 新增 evaluator 校验，以及 Codex 和 Claude Code 风格运行时适配。

### v4.0.0

- 引入闭环多智能体协议。
- 新增 artifact 初始化、报告校验、角色边界、停止条件和 evaluator 模板。

---

## 许可证

当前仓库尚未包含 license 文件。
