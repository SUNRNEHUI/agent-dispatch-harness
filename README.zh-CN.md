# Agent Dispatch Harness

简体中文 | [English](README.md)

Agent Dispatch Harness（原名 Multi-Agent Dispatcher）是一套**跨模型任务执行 OS**。它帮助 Codex / Claude Code / Grok 等编码代理按风险选择最轻流程：从单次 Direct 修复，到带证据门槛的 Full harness 长任务，而不是“永远多智能体”或“永远写大 harness”。

当前版本：**v6.0.0** · 2026-07-14

---

## 概览

本 skill 强调比例化执行：

```text
用户意图 → 密度判断 →（可选）Spec Synthesis → 执行 → 证据 → 完成
```

口头“多 agent”只代表可以评估是否派工，不等于必须派工。模糊目标应先编译成成功条件 / 假完成 / 验收规则，再写代码。长、高风险、可续跑的工作才使用持久化 Full harness。

主代理始终负责：

- 密度 / 模式选择（Direct、Lite、Full）
- 目标含糊时的 Spec Synthesis
- 目标、非目标、责任边界和验证要求
- 仅在责任边界清晰时启动子代理
- 合并结果与冲突处理
- 在宣布完成前**亲自复核**关键证据

子代理只执行有边界的切片，不拥有最终验收权。

---

## 核心能力

- **密度判断：** 在能抑制假完成的前提下选最轻模式（Direct → synthesis → Lite → Full）。
- **Spec Synthesis：** 把模糊或“更快/更好”类目标编译成可执行合同。
- **选择性调度：** 仅在 ownership 干净且协调成本低于收益时派工。
- **Full harness 持久化：** `run_state`、验收清单、trace、任务合同位于 `workspace/<slug>/`。
- **运行时 TDD 证据：** strict TDD / test-first / substitute / not_applicable，配合 wrapper 生成的 trace。
- **证据化验收：** 测试、构建、日志、浏览器、截图、CI 或 evaluator；禁止仅靠自评。
- **计划质量评分（可选）：** `score_harness.py` 只评 harness 完整度，**不是**产品 PASS。
- **运行时适配：** Codex、Claude Code、universal。
- **干净打包：** runtime-only 安装包，不含文档、缓存或私有配置。

---

## 执行模式

| 模式 | 适用场景 | 是否写盘 | 行为 |
| --- | --- | --- | --- |
| **Direct** | 小、清楚、假完成风险低 | 否 | 主代理直接实现并验证 |
| **Direct+** | 清晰的 2–5 步、单一 owner | 仅可选聊天计划 | 不写 Full `workspace/` |
| **Lite** | 中等任务、可并行且 ownership 干净 | 短计划 / 紧凑报告 | 有限 worker；默认无完整 registry |
| **Full** | 长任务、高风险、可续跑、需 evaluator / worktree | `workspace/<slug>/` | 完整状态、验收、trace、TDD gate |

**Spec Synthesis** 不是第四种模式：目标含糊、改进型或易假完成时先编译。紧凑版在聊天或短笔记中完成；Full 版用 `init_run.py --with-synthesis` 生成 stage `0.1`。

硬规则：

- 多 agent 用词 ≠ 必须派工
- 单 owner 中等步骤 → Direct+，不要 Lite 演戏
- 模糊目标默认不等于 Full harness
- 改进型任务先定义终点指标与基线，再“优化”

---

## 适用场景

适合在以下情况优先加载本 skill：

- 多智能体 / 子代理 / DAG / worktree / 分头处理
- 需要 Spec Synthesis 的模糊目标（“更快”“更好”“更专业”）
- 可续跑、需证据验收的长协调
- 需要判断流程该厚还是该薄，避免烧 token

小而清楚的任务不要强行 Full 或派工。未授权且无收益时保持单代理。

---

## 运行流程

```text
上下文接入
-> 密度判断：Direct / synthesis / Lite / Full
-> 可选 Spec Synthesis（成功、假完成、验收规则）
-> 执行选定模式
   Direct：实现、验证、汇报
   Lite：协调有边界的切片、验证、汇报
   Full：capability、artifact、DAG、worker、TDD gate、evaluator
-> 主代理复核关键证据
-> 合并 / 交接
```

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

---

## 安装

克隆仓库：

```bash
git clone https://github.com/SUNRNEHUI/agent-dispatch-harness.git
cd agent-dispatch-harness
```

生成干净的 runtime 包：

```bash
python3 scripts/sync_version.py
python3 scripts/package_skill.py --verify-source
python3 scripts/package_skill.py --output /tmp/agent-dispatch-harness-runtime --force
```

安装到 Codex：

```bash
mkdir -p ~/.codex/skills/agent-dispatch-harness
rsync -a --delete /tmp/agent-dispatch-harness-runtime/ ~/.codex/skills/agent-dispatch-harness/
python3 scripts/package_skill.py --check ~/.codex/skills/agent-dispatch-harness
```

runtime 包只包含 skill 运行时需要的文件。

---

## 从旧名称迁移

早期版本使用 `multi-agent-dispatcher` 作为公开包名，一些本地安装也使用过 `multi-agent-orchestrator` 作为 Codex skill 目录。新的安装和公开传播应统一使用 `agent-dispatch-harness`。

升级已有本地安装时，先安装新的 runtime 目录；如果旧目录仍存在且不再需要，可以删除：

```bash
rm -rf ~/.codex/skills/multi-agent-dispatcher ~/.codex/skills/multi-agent-orchestrator
```

这样可以避免同一套工作流以多个 skill 名称重复出现。

---

## Runtime 包内容

runtime 包包含：

- `VERSION`、`SKILL.md`、`master-prompt.md`、`sub-prompt.md`、`agents/openai.yaml`
- `adapters/` — `codex.md`、`claude-code.md`、`universal.md`
- `references/` — 协议、lane、Spec Synthesis、proportionality、TDD gates、示例
- `templates/` — Full / Lite harness 模板
- `scripts/` — `init_run.py`、`harness_test_run.py`、`runtime_state.py`、`validate_workspace.py`、
  `status.py`、`tdd_gate_check.py`、`validate_report.py`、`score_harness.py`、`score_skill_protocol.py`

权威文件清单以 `scripts/package_skill.py:RUNTIME_FILES` 为准。

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

---

## 仓库结构

```text
agent-dispatch-harness/
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
- [Claude Code adapter](adapters/claude-code.md)
- [Harness protocol reference](references/harness-protocol.md)

适配文档不改变协议，只把同一组 gate、artifact、证据规则和回退行为映射到可用的运行时控制能力上。

---

## 与 Superpowers 的关系

本项目是独立实现，不依赖 Superpowers 运行。

本项目在设计上参考了 [obra/superpowers](https://github.com/obra/superpowers) 中的部分工程实践。Superpowers 是 Jesse Vincent 创建的软件开发方法体系。Agent Dispatch Harness 借鉴的方向包括 test-first evidence、fresh-context sub-agents、review gates、worktree isolation 和 verification before completion。

本项目不复制 Superpowers 的 skill 正文，也不要求安装 Superpowers 插件。二者关系如下：

```text
agent-dispatch-harness = 路由与 harness 权威
Superpowers-style methods = 可选的工程支持方法
```

模式选择始终先执行。只有当支持方法适合当前执行模式时，才会使用这些方法。

---

## 版本管理

单一来源：

```bash
cat VERSION
python3 scripts/sync_version.py --fix --date 2026-07-14
python3 scripts/sync_version.py
python3 scripts/package_skill.py --verify-source
python3 scripts/test_runtime_behavior.py
```

发布清单：更新 `VERSION` → `sync_version.py --fix` → 同步中英文 Release History → 跑测试 → `release/vX.Y.Z` 分支提交 → 合入 main → 打 `vX.Y.Z` tag → GitHub Release。

---

## 版本历史

### v6.0.0

- 重新定位为**通用任务 OS**：按密度选 Direct / Lite / Full，而非多智能体优先。
- 新增 **Spec Synthesis**（`references/spec-synthesis.md`，`init_run.py --with-synthesis`）。
- 新增 proportionality 与渐进加载（`references/proportionality.md`，缩短 `SKILL.md` / prompts）。
- 新增 universal adapter 与可选 harness 评分（`adapters/universal.md`，`score_harness.py`，`score_skill_protocol.py`）。
- 强化验收语言：主代理必须复核关键证据；`score_harness` 高分 ≠ 产品完成。
- 保留 mainline 运行时安全：manager state/trace API、原子 JSON、锁定 JSONL、timeout 预算、workspace 绑定校验。
- 重写公开 README，并文档化版本管理。

### v5.11.0

- 精简编排并加强完成置信度门槛（见 GitHub Releases 标签说明）。

### v5.10.0

- GPT-5.6 相关路由说明（见 GitHub Releases 标签说明）。

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

运行时协调使用 cooperative manager-only state/trace API guard、JSON 原子替换、JSONL 加锁追加，并从独立 git 环境读取 workspace identity。该 guard 可被同一用户进程直接写文件绕过；隔离依赖 native sandbox/OS permissions。验证默认 1800 秒，且 timeout 必须不超过 runtime budget。

## 许可证

当前仓库尚未包含 license 文件。
