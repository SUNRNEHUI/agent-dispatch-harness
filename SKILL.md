---
name: multi-agent-dispatcher
description: Use when user says "帮我计划一下" or "做XXX" that requires multi-task splitting — breaks down tasks to task_plan.md, auto-dispatches sub-agents, manages entire flow without interruption.
---

# Multi-Agent Task Dispatcher

> 上下文窗口 = RAM（易失，有限）
> 文件系统 = 磁盘（持久，无限）
> → 重要的东西要写到磁盘。

## 核心目标

- **计划落盘**：拆分任务 → task_plan.md（不放上下文，防止丢失）
- **自动执行**：无需用户确认，主 agent 直接调度
- **上下文干净**：子 agent 只看到最小输入
- **全程控制**：主 agent 管理、合并、调度、检查整个流程

## 触发条件

| 用户表达 | 动作 |
|---------|------|
| "帮我计划一下" | 拆分任务 → task_plan.md → 开始调度 |
| "做XXX"（需要多步骤） | 拆分任务 → task_plan.md → 开始调度 |
| "开始执行" | 检查 task_plan.md → 继续调度 pending 任务 |
| task_plan.md 存在 + 有 pending | 继续调度 |

## 执行流程

```
用户: "帮我计划一下做一个待办应用"

主 agent:
1. 分析需求，拆分为任务
2. 写入 task_plan.md（落盘，不放上下文）
3. 创建 progress.md 记录执行过程
4. 自动启动子 agent（无需确认）
5. 监控完成状态
6. 验证结果
7. 继续调度下一批，直到全部完成
8. 合并结果，向用户报告
```

## 文件结构

```
project/
├── task_plan.md        # 任务计划（SSOT）
├── findings.md         # 决策记录
├── progress.md         # 执行进度
├── SUMMARY/            # 子 agent 摘要
└── src/                # 实际代码
```

| 文件 | 用途 | 更新时机 |
|------|------|----------|
| task_plan.md | 任务列表、状态、依赖 | 任务拆分、状态变化 |
| findings.md | 关键决策、设计选择 | 任何重要发现 |
| progress.md | 执行日志、测试结果 | 全程持续 |

## 任务状态机

```
pending → running → completed/verified
                    ↘ failed → retry (最多 3 次)
                              → fatal (需要人工介入)
```

| 状态 | 含义 | 流转条件 |
|------|------|----------|
| pending | 待执行 | 依赖全部完成 |
| running | 执行中 | 启动子 agent |
| completed | 已完成 | 子 agent 返回成功 |
| verified | 已验证 | 主 agent 质量检查通过 |
| failed | 失败 | 子 agent 返回错误 |
| fatal | 致命 | 重试超过上限 |

## Step 1: 任务拆分

分析用户需求，写入 task_plan.md（markdown 格式）：

```markdown
# 任务计划

## 目标
做一个待办应用

## 任务列表

### Phase 1 - 结构
- [ ] T1-1: 创建 HTML 基础结构 (priority: 1, depends_on: [])

### Phase 2 - 样式和逻辑
- [ ] T2-1: 创建 CSS 样式 (priority: 2, depends_on: [])
- [ ] T2-2: 创建 JavaScript 逻辑 (priority: 2, depends_on: [])

### Phase 3 - 验证
- [ ] T3-1: 验证所有文件正常工作 (priority: 3, depends_on: [T1-1, T2-1, T2-2])

## 配置
- max_parallel: 3
- retry_policy: { max_attempts: 3, backoff: [5s, 25s, 125s] }
```

## Step 2: 自动调度

扫描 pending 任务（依赖满足），启动子 agent：

```bash
# 扫描可运行任务
grep -E "^- \[ \]" task_plan.md | grep "depends_on:" | ...
```

## Step 3: 子 agent 输入

每个子 agent 只收到最小输入：

```json
{
  "task_id": "T2-1",
  "description": "创建 CSS 样式",
  "depends_on": [],
  "artifacts_expected": ["styles.css"],
  "working_dir": "/path/to/project"
}
```

## Step 4: 5 问恢复测试

上下文压缩后，读取文件恢复：

1. **我在哪？** → task_plan.md 里的 pending 任务
2. **我要去哪？** → 未完成的任务
3. **目标是什么？** → task_plan.md 顶部的目标
4. **学到了什么？** → findings.md
5. **做了什么？** → progress.md

## 质量验证

| 验证项 | 方式 |
|--------|------|
| 格式验证 | SUMMARY 符合 schema |
| 产物验证 | artifacts 存在且非空 |
| 逻辑验证 | （可选）lint/test |

## 失败处理

| 错误类型 | 处理 |
|----------|------|
| retryable | 指数退避重试（5s → 25s → 125s） |
| fatal | 标记 fatal，通知用户 |

## 模板文件

- `master-prompt.md` - 主 agent 调度逻辑
- `sub-prompt.md` - 子 agent 执行规范
- `summary.schema.json` - 摘要 schema

---

*Multi-Agent Dispatcher v3.0 | 2026-04-23*
