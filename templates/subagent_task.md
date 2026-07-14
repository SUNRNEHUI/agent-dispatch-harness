# Sub-Agent Task

任务 X.Y: <任务名>

## Goal

<单一职责；写清完成长什么样>

## Dependencies

- 

## Allowed Scope

-

不得修改范围外文件，除非 manager 明确扩权。

## Inputs

- 路径/模块：
- 契约/接口：
- 约束：
- 假成功提醒（本任务相关）：

## Testing Gate / Verification

- Gate mode：strict_tdd / test_first_evidence / substitute / not_applicable
- Strict TDD：RED command/result/failure reason → implement → GREEN → refactor check
- Test-first evidence：先有失败/缺口证据，再改生产代码
- Substitute：必须写 no-test reason + substitute check
- 命令：
- 环境/浏览器检查：
- 期望证据路径：
- acceptance_registry 关联：
- run_state 更新建议：

## Required Outputs

- 代码/文档：
- 报告：<artifact-dir>/X.Y-报告.md
- 证据：命令、退出码、输出摘要或日志路径；不能只写“已验证”
- 未验证路径：

## PASS

<可判定条件；避免“更好/差不多”>

## Stop

- 范围扩大超出 allowed scope
- 连续验证失败且无新诊断
- 需要高影响/破坏性操作
- 无法生成关键证据，只能推测
- 与其他 agent 文件所有权冲突

## Return Format

```text
状态：已完成 / 失败 / 需要决策
报告：<artifact-dir>/X.Y-报告.md
产出：N 个文件（列出路径）
决策点：[如有，一句话描述]
```
