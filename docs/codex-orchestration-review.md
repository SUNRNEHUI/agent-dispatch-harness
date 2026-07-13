# Codex-Orchestration 对照评估

评估对象：`Cjbuilds/Codex-Orchestration`

参考提交：`a1d9c546665c3253cdcaa8fe5c0c060199a6126c`（2026-07-12）

本报告的目的不是复制另一个插件，而是判断哪些机制能让 Agent Dispatch Harness 更安全、更可信、更省 token。报告位于 `docs/`，不会进入 runtime 包，避免把维护分析转成每次任务都要加载的上下文。

## 结论

值得吸收的是“薄路由层 + 强边界 + 可验证状态”，而不是更多角色和更长的编排链。我们的核心仍然是 Direct/Lite/Full mode router；Codex 原生调度仍由当前任务的 root model 负责。

## 吸收

| 思路 | 在本项目中的落点 | 原因 |
| --- | --- | --- |
| 单一 root | `SKILL.md` 明确 active parent model 是唯一 root orchestrator | 避免出现 root、scheduler、advisor 三套互相覆盖的决策源 |
| `no subagents` 优先 | 作为显式用户约束，不受 worker 上限或保存偏好影响 | 安全优先，也直接减少无效 token |
| 真实路由状态 | `references/model-routing.md` 区分 `requested`、`accepted`、`used and confirmed`、`inherited root` | 不把 prompt 偏好或子 agent 自报当成模型运行证据 |
| 严格状态出口 | `scripts/status.py --require-high-confidence` | 人读状态默认保持轻量，CI 或发布 gate 才强制失败 |
| 失败闭环 | 保留现有 budget、evidence gap、blocked 和 rollback 规则 | 对方的 dry-run、恢复和 fail-closed 思路适合转化为协议边界，而不是复制其配置器 |
| 发布卫生 | 继续保持单一 `VERSION`、runtime-only package、tag/release 校验 | 这是安全可信 harness 的供应链基础 |

## 取消或不引入

| 低效或高风险做法 | 决策 | 原因 |
| --- | --- | --- |
| 第二个 orchestrator | 取消 | Codex 当前任务已经有 root；再加 scheduler 只会复制计划、handoff 和验收上下文 |
| 默认 advisor 或每次计划审查 | 取消默认行为 | 简单任务的 advisor token 通常不能抵消新增上下文和整合成本；只在高风险、歧义或独立证据不足时启用 review |
| Claude/Fable 跨 provider bridge | 不引入 | 需要登录、MCP launcher、运行时身份确认和两阶段恢复，维护面远大于当前 harness 的核心收益 |
| 持久化全局 native routing 配置器 | 不引入 | 会修改用户级配置并引入兼容矩阵、回滚状态和跨客户端竞态；本项目保持 task-local、runtime-neutral 的策略 |
| 全量 parent transcript fork | 取消 | 重复上下文是主要 token 浪费来源；worker 只接收 task-local packet |
| 无限 follow-up / 固定填满线程 | 取消 | GPT-5.6 的线程上限只是能力 ceiling，不是 fan-out 目标；没有新证据就停止 |
| 小任务的 TDD、双 reviewer、worktree、Full artifact 套餐 | 取消默认串联 | 这些是风险触发器，不是每个任务的必经流程；Direct 和 Lite 必须保持低仪式成本 |
| 把原始日志直接回传 root | 取消默认行为 | 只回 compact report 和证据路径，失败或验收需要时才带原始片段 |

## 保留边界

不会因为追求省 token 而删除以下硬控制：manager-owned acceptance、显式 token budget、未知计量时阻断 accepted、权限/发布/破坏性操作 stop condition、Full run 的可续跑状态，以及最终 diff 和验证检查。效率优化只能减少不必要的调度和上下文，不能减少安全证据。

## 后续度量

本次只做策略和运行时门槛优化，没有真实 GPT-5.6 Luna/Terra/Sol 的端到端 benchmark，因此不宣称固定 token 或成本节省比例。后续应使用代表性任务比较成功率、证据质量、总 token、延迟、工具调用、重试和成本；只有质量与安全 gate 不下降时才保留进一步的路由调整。
