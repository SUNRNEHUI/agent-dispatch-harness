# Multi-Agent Dispatcher

**File-Driven Multi-Agent Task Orchestration Framework for Claude Code**

> **Context window = RAM** — volatile, finite. **Filesystem = Disk** — persistent, unlimited. When context is scarce, write to disk.

---

## The Problem

Large Language Models operate under a fundamental constraint: **context is finite and precious**. Every token spent on task state is a token not spent on reasoning. In long-running agentic workflows, this creates a compounding problem:

| Without Persistence | With Persistence |
|---------------------|------------------|
| Task state lives in context | Task state lives on disk |
| Lost on context overflow | Survives any interruption |
| Grows linearly with complexity | Bounded by disk space |
| Fragile, hard to audit | Transparent, easy to review |

Existing approaches solve this with elaborate in-memory state management, complex orchestration schemas, or rigid pipeline definitions. We took a different approach: **treat the filesystem as the source of truth.**

---

## Core Principles

### 1. Task State Persistence

All task decomposition, scheduling decisions, and execution state live in human-readable markdown files — not in model context.

- `task_plan.md` — Master task list with dependency graph and status
- `progress.md` — Real-time execution log
- `findings.md` — Architectural decisions and learnings

### 2. Autonomous Execution

Once tasks are decomposed, the dispatcher operates without interruption. No confirmation prompts, no manual scheduling — the master agent coordinates sub-agents until completion.

### 3. Clean Sub-Agent Context

Each sub-agent receives only the minimal input it needs:
```json
{
  "task_id": "T2-1",
  "description": "Implement CSS styling",
  "depends_on": [],
  "artifacts_expected": ["styles.css"],
  "working_dir": "/path/to/project"
}
```
No cross-contamination, no information leakage between agents.

### 4. Crash Recovery

When context is compressed (or a session is interrupted), the agent recovers via a 5-question self-diagnosis:

1. **Where am I?** → `[~]` tasks in `task_plan.md`
2. **Where am I going?** → `[ ]` pending tasks
3. **What's the goal?** → Top of `task_plan.md`
4. **What have I learned?** → `findings.md`
5. **What happened?** → `progress.md`

---

## Architecture

```
User Input
    │
    ▼
┌─────────────┐
│ Master Agent │  ← Decompiles → Writes task_plan.md
└─────────────┘
    │
    ├── T1-1 ──┬──→ Sub-Agent-1
    │
    ├── T2-1 ──┼──→ Sub-Agent-2  (parallel execution)
    │
    └── T2-2 ──┴──→ Sub-Agent-3
    │
    ▼
File System (SSOT)
    │
    ▼
Master Agent ← Monitors → Sub-Agent Results
    │
    ▼
User Report
```

### State Machine

```
pending → running → completed/verified
                    ↘ failed → retry (max 3) → fatal
```

---

## Why This Approach

### Token Efficiency

By offloading task state to files, the context window is reserved for high-value operations: reasoning, code generation, and decision-making. Sub-agents operate in isolated, minimal contexts.

### Horizontal Scalability

Tasks with no interdependencies execute in parallel. The dispatcher automatically batches and sequences based on dependency graphs.

### Failure Isolation

A sub-agent failure doesn't cascade. The state machine handles retries with exponential backoff, and fatal failures are logged for human review.

### Auditability

Every decision, every state change, every artifact is captured in plain text. You can reconstruct the entire execution history from the files.

---

## Quick Start

```bash
# Install
cp -r multi-agent-dispatcher ~/.claude/skills/

# Trigger (say this to Claude Code)
"帮我计划一下做一个待办应用"
```

The dispatcher will:
1. Decompose the request into tasks
2. Write `task_plan.md` with the execution plan
3. Auto-dispatch sub-agents in parallel
4. Monitor and verify results
5. Report completion

---

## File Structure

```
skill/
├── SKILL.md              # Skill entry point
├── master-prompt.md     # Master agent orchestration logic
└── sub-prompt.md        # Sub-agent execution spec

project/
├── task_plan.md         # Task plan & dependency graph
├── findings.md          # Architectural decisions
├── progress.md          # Execution log
└── src/                 # Generated artifacts
```

---

## Comparison

| Feature | Traditional | Multi-Agent Dispatcher |
|---------|-------------|------------------------|
| Task persistence | In-memory | File-based |
| Context usage | High (grows with tasks) | Minimal (offloaded) |
| Recovery after crash | Requires full restart | Auto-resume from files |
| Parallel execution | Manual scheduling | Automatic dependency-aware |
| Audit trail | Hidden in context | Human-readable files |
| Sub-agent isolation | Often coupled | Guaranteed minimal input |

---

## Credits

Built for Claude Code Agent Skills system.

*v3.0 | 2026-04-23*
