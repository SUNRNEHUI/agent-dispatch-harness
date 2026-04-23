# multi-agent-dispatcher

文件驱动型多代理任务调度框架 — 用于 Claude Code

> 上下文窗口 = RAM（易失，有限）
> 文件系统 = 磁盘（持久，无限）
> → 重要的东西要写到磁盘。

## 核心特性

- **计划落盘**：任务写入 `task_plan.md`，不放在上下文中
- **自动执行**：拆分任务后立即开始调度，无需用户确认
- **上下文干净**：子 agent 只看到最小输入
- **中断可恢复**：所有状态在文件中，断点后自动续传

## 工作流

```
用户: "帮我计划一下做一个待办应用"
  ↓
主 Agent:
1. 分析需求，拆分为任务
2. 写入 task_plan.md
3. 自动启动子 agent（并行执行）
4. 监控完成状态，验证结果
5. 继续调度下一批，直到全部完成
6. 合并结果，向用户报告
```

## 文件结构

```
skill/
├── SKILL.md           # Skill 入口（161 行）
├── master-prompt.md   # 主 Agent 调度逻辑（142 行）
└── sub-prompt.md      # 子 Agent 执行规范（100 行）

项目/
├── task_plan.md        # 任务计划（SSOT）
├── findings.md         # 决策记录
├── progress.md         # 执行进度
└── src/                # 实际代码
```

## 任务状态机

```
pending → running → completed/verified
                    ↘ failed → retry (最多 3 次)
```

| 状态 | 含义 |
|------|------|
| `[ ]` pending | 待执行 |
| `[~]` running | 执行中 |
| `[x]` verified | 已验证 |

## 5 问恢复测试

上下文压缩后，通过文件恢复：

1. **我在哪？** → `task_plan.md` 里的 `[~]` 任务
2. **我要去哪？** → `[ ]` 待执行任务
3. **目标是什么？** → `task_plan.md` 顶部
4. **学到了什么？** → `findings.md`
5. **做了什么？** → `progress.md`

## 子 Agent 输入

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

## 安装

将此文件夹放入 Claude Code 的 skills 目录：

```bash
cp -r multi-agent-dispatcher ~/.claude/skills/
```

---

*v3.0 | 2026-04-23*
