# Sub-Agent Task

任务 X.Y: <任务名>

## 目标

<单一职责，避免跨边界修改>

## 输入

- 路径/模块：
- 契约/接口：
- 约束：

## 允许修改范围

-

## 产出

- 代码：
- 报告：<artifact-dir>/X.Y-报告.md
- 证据：必须包含命令、输出摘要、路径或截图/日志位置；不能只写“已验证”
- TDD / 替代验证记录：必须填写报告中的 `Test-First Or Substitute Verification`；不能省略 gate mode
- 未验证路径：列出未跑通、只静态检查、依赖外部环境或仍需主 agent/evaluator 验证的路径

## 验证

- Gate mode：strict_tdd / test_first_evidence / substitute / not_applicable
- Strict TDD：若用户或项目明确要求 TDD，必须提供 RED command/result/failure reason、GREEN command/result 和 refactor check
- Test-first evidence：若是代码行为变更且存在有意义测试，必须先给失败或暴露缺口的测试证据，再实现并跑通过
- Substitute：若无测试基础设施、docs/config-only 或测试成本明显不合理，必须说明 no-test reason 并给 substitute check
- 命令：
- 浏览器/环境检查：
- 期望证据：
- acceptance_registry.json 关联项：
- run_state.json 更新建议：task status / evidence / stop_reason

## 停止条件

- 范围扩大
- 连续验证失败
- 需要高影响操作
- 无法在授权范围内完成
- 发现其他 agent 的文件所有权冲突
- 关键证据无法生成，或只能给出推测性结论

## 返回格式

```text
状态：已完成 / 失败 / 需要决策
报告：<artifact-dir>/X.Y-报告.md
产出：N 个文件（列出路径）
决策点：[如有，一句话描述]
```
