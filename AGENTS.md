# AGENTS.md

本文件是 `agent-dispatch-harness` 项目的项目级规则。它覆盖用户级通用规则中与本项目冲突的部分。

## 项目定位

本仓库维护一个跨模型可用的 **任务执行 OS / agent skill**（Codex、Claude Code、Grok 等）。目标是按风险选择最轻执行密度，而不是把每个任务都变成多智能体编排。

核心原则：

- 密度优先：Direct → Spec Synthesis → Lite → Full；口头「多 agent」不等于必须派工。
- 模糊目标先 Spec Synthesis（成功条件 / 假完成 / 验收规则），再写代码。
- Full Harness 只用于长任务、高风险、可续跑、需要 evaluator 或证据化验收的工作。
- 只接受外部证据；`score_harness` 高分不等于产品完成。
- State 和 Memory 必须分离。单次 run artifact 只保存本次任务状态和审计日志，跨任务经验只能作为 memory candidate，不能自动晋升。

## 主要文件

- `SKILL.md`：Codex skill 的入口协议和触发说明。
- `VERSION`：当前发布版本的单一来源。
- `README.md` / `README.zh-CN.md`：公开说明，必须保持英文和中文同步。
- `references/`：可按需加载的协议、lane、边界和评估说明。
- `templates/`：Lite 和 Full Harness 运行时 artifact 模板。
- `scripts/init_run.py`：初始化 Lite 或 Full Harness run artifact。
- `scripts/status.py`：从 `run_state.json` 派生单屏状态摘要。
- `scripts/validate_report.py`：校验 spec、progress、lite_plan、lite_review、evaluator 和 run_state 结构。
- `scripts/tdd_gate_check.py`：TDD trace gate 检查。
- `scripts/package_skill.py`：生成 runtime-only skill 包。

## 修改规则

- 修改 skill 行为时，优先改 `SKILL.md` 和相关 `references/`，再同步模板和脚本。
- 修改公开行为或版本时，必须同步 `README.md` 和 `README.zh-CN.md`。
- 修改当前版本时，先改 `VERSION`，再运行 `python3 scripts/sync_version.py --fix`。
- 修改 runtime 内容时，必须同步 `scripts/package_skill.py` 的包含/排除逻辑。
- 不要把 `workspace/`、缓存、session 日志、私有配置或生成 artifact 加入 runtime 包。
- 不要把本地安装目录 `~/.codex/skills/agent-dispatch-harness` 当成源码。源码以本仓库为准。
- 保持 diff 小而聚焦，不做无关重排、格式化或重命名。

## TDD 和验证

改动脚本或模板结构时，优先使用最小可行 Testing Gate：

1. 先明确要拒绝或接受的结构。
2. 能写负例时，先用现有 validator 或临时 fixture 证明当前缺口。
3. 再修改脚本或模板。
4. 最后运行相关验证命令。

常用验证命令：

```bash
python3 -m json.tool templates/run_state.json >/dev/null
python3 -m py_compile scripts/init_run.py scripts/package_skill.py scripts/status.py scripts/sync_version.py scripts/validate_report.py scripts/harness_test_run.py scripts/tdd_gate_check.py scripts/test_runtime_behavior.py
git diff --check
python3 scripts/sync_version.py
python3 scripts/init_run.py --mode full --project-root /tmp/adh-smoke-full --title "full smoke" --agents docs,review --force
python3 scripts/init_run.py --mode lite --project-root /tmp/adh-smoke-lite --title "lite smoke" --agents docs,adapter --force
python3 scripts/validate_report.py /tmp/adh-smoke-full/workspace/full-smoke/task_spec.md --type spec
python3 scripts/validate_report.py /tmp/adh-smoke-full/workspace/full-smoke/progress.md --type progress
python3 scripts/validate_report.py /tmp/adh-smoke-full/workspace/full-smoke/evaluator_report.md --type evaluator
python3 scripts/validate_report.py /tmp/adh-smoke-lite/workspace/lite-smoke/lite_plan.md --type lite_plan
python3 scripts/status.py /tmp/adh-smoke-full/workspace/full-smoke/run_state.json
python3 scripts/test_runtime_behavior.py
python3 scripts/package_skill.py --verify-source
python3 scripts/package_skill.py --output /tmp/agent-dispatch-harness-runtime --force
```

如果改动影响 TDD trace：

```bash
python3 scripts/tdd_gate_check.py templates/tdd_trace.jsonl
```

如果同步本地安装：

```bash
rsync -a --delete /tmp/agent-dispatch-harness-runtime/ /Users/sunrenhui/.codex/skills/agent-dispatch-harness/
python3 scripts/package_skill.py --check /Users/sunrenhui/.codex/skills/agent-dispatch-harness
```

## 发布规则

发布前必须确认：

- `VERSION`、`README.md`、`README.zh-CN.md` 与 `SKILL.md` 当前版本一致。
- release history 中英同步。
- runtime 包能干净生成。
- 本地安装目录与 runtime 包一致。
- `git status` 中没有意外文件。

GitHub 发布通常包含：

- commit
- tag，例如 `vX.Y.Z`
- push main
- push tag
- GitHub release notes
- runtime zip，如需要

## 多 agent 使用

本项目可以使用多 agent 辅助开发，但主 agent 必须保留最终责任：

- 子 agent 适合做只读审查、独立实现、对抗式评估、文档一致性检查。
- 修改同一文件前要明确 owner，避免并行冲突。
- reviewer/evaluator 默认应在实现任务之后运行，不应和被审查实现并行，除非它只审查已存在 artifact。
- 主 agent 合并结果后必须亲自 review diff 和运行验证。

## 当前上下文

如果从新线程继续，请先读取桌面的项目 handoff：

`/Users/sunrenhui/Desktop/agent-dispatch-harness-project-handoff.md`

再读取完整自动导出的线程 handoff：

`/Users/sunrenhui/Desktop/20260708-171231-codex-019e62a7-full-Files-mentioned-by-the-user--多-agent.md`
