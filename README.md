# Multi-Agent Dispatcher

[简体中文](README.zh-CN.md) | English

Multi-Agent Dispatcher is an agent skill for routing explicit multi-agent requests into the smallest execution mode that can complete the work reliably. It avoids unnecessary delegation for small tasks and provides a durable harness for long, risky, resumable, evidence-verified work.

Current release: **v5.2.2** · 2026-05-28

---

## Overview

Multi-agent execution is useful only when the work has clear independent ownership boundaries or requires durable coordination. This skill separates authorization from execution: a user may request multi-agent work, but the manager agent still decides whether delegation improves the result.

The manager remains responsible for:

- selecting the execution mode
- defining scope, non-goals, ownership, and verification requirements
- assigning bounded work to sub-agents when delegation is justified
- merging results and resolving conflicts
- verifying acceptance evidence before claiming completion

Sub-agents are used only for bounded execution, investigation, review, or evaluation tasks. They do not replace the manager's responsibility for final acceptance.

---

## Core Capabilities

- **Mode selection:** choose Direct, Lite, or Full execution before creating workers or artifacts.
- **Selective delegation:** dispatch sub-agents only when the task has clean ownership boundaries.
- **Durable state:** preserve task state for long or resumable work under a project workspace directory.
- **Evidence-based acceptance:** require tests, build output, logs, browser checks, screenshots, CI, readback, or evaluator reports before completion.
- **Runtime adapters:** map the same protocol to Codex, Claude Code, or similar coding-agent environments.
- **Clean packaging:** generate a runtime-only install package without repository docs, local caches, generated workspaces, or private configuration.

---

## Execution Modes

| Mode | Use When | Behavior |
| --- | --- | --- |
| **Direct** | The task is small, local, sequential, or cheaper for one agent to complete. | No sub-agents and no orchestration artifacts. The manager executes and verifies directly. |
| **Lite** | The task has a few separable slices, but does not need a durable harness. | The manager uses a short plan, bounded ownership, compact reports, and targeted verification. |
| **Full** | The task is long, risky, resumable, parallel, evaluator-heavy, or benefits from worktree isolation. | The manager runs the full harness with capability records, state files, acceptance registry, trace, reports, and verification gates. |

Explicit multi-agent wording authorizes mode selection. It does not automatically require multiple workers.

---

## When To Use

Use this skill when the user explicitly asks for:

- multi-agent work
- sub-agents
- delegated agent work
- parallel agents
- DAG scheduling
- worktree-based parallel execution
- 分头处理 / 分别派 / 拆给不同 agent
- resumable or evidence-verified long-running coordination

Do not use this skill only because a task is large. If the user has not authorized multi-agent execution, continue with the normal single-agent workflow or briefly propose multi-agent coordination when it would materially reduce risk.

---

## Operating Flow

```text
Context Intake
-> Mode Selection: Direct / Lite / Full
-> Execute Selected Mode
   Direct: implement, verify, report
   Lite: coordinate bounded slices, verify, report
   Full: run capability gate, acceptance registry, state machine, trace, evaluator
-> Merge / Handoff
```

The manager should always choose the lightest mode that preserves quality and verification.

---

## Full Harness Protocol

Full mode uses a durable protocol for work that needs stronger coordination.

### 1. Mode Selection Gate

The manager records why Direct, Lite, or Full mode is appropriate. Full mode is justified by independent ownership surfaces, long or resumable scope, material verification risk, evaluator value, or isolation and rollback value.

### 2. Capability Gate

Before assigning work, the manager records the runtime capabilities that are actually available:

- real sub-agent or delegation mechanism
- filesystem write access
- shell and sandbox limits
- worktree support
- browser or UI verification capability
- instruction files or hooks that can carry protocol rules
- external services, credentials, and network assumptions

If a capability is unavailable, the manager must choose a fallback such as sequential execution, narrower scope, a decision request, or a stop state.

### 3. State Machine

Full mode advances through explicit states:

```text
INTAKE -> GATED -> SPECIFIED -> DISPATCHED -> REPORTED -> EVALUATING -> ACCEPTED -> HANDED_OFF
```

Stop states are first-class:

```text
BLOCKED -> NEEDS_DECISION -> FAILED
```

Each state transition should leave a compact trace entry with the reason, owner, evidence path, and next state.

### 4. Acceptance Registry

Acceptance criteria are tracked as structured records. Each record should include:

- criterion
- owner
- required evidence
- status: `pending`, `pass`, `fail`, `blocked`, or `scoped_out`
- evidence path or command result summary

The manager cannot claim completion while required criteria remain unverified.

### 5. Budget Circuit Breaker

Each stage should have a budget envelope for time, context, tool calls, retries, cost, and external side effects. When a stage exceeds the envelope, the manager records the stop reason and chooses whether to continue, split, reduce scope, or ask for a decision.

### 6. Trace

Trace records the minimum durable evidence needed to resume and audit a run:

- capability gate result
- state transitions
- worker report paths
- evaluator result
- budget stop or retry reason
- final acceptance registry

Chat history is not treated as durable task state.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/SUNRNEHUI/multi-agent-dispatcher.git
cd multi-agent-dispatcher
```

Create a clean runtime package:

```bash
python3 scripts/package_skill.py --output /tmp/multi-agent-dispatcher-runtime --force
```

Install the runtime package into Codex:

```bash
mkdir -p ~/.codex/skills/multi-agent-dispatcher
rsync -a --delete /tmp/multi-agent-dispatcher-runtime/ ~/.codex/skills/multi-agent-dispatcher/
```

The runtime package contains only the files needed by the skill at execution time.

---

## Runtime Package Contents

The runtime package includes:

- `SKILL.md`
- `master-prompt.md`
- `sub-prompt.md`
- `agents/openai.yaml`
- `adapters/`
- `references/`
- `templates/`
- `scripts/init_run.py`
- `scripts/validate_report.py`

It intentionally excludes:

- `README.md`
- `README.zh-CN.md`
- `scripts/package_skill.py`
- `.git`
- generated workspace artifacts
- local memory files
- session logs
- caches and bytecode
- private configuration
- credentials or API keys

---

## Usage Examples

Explicit multi-agent request:

```text
This project has frontend, backend, and test work. Use multiple agents where useful, and provide verification evidence.
```

Small task with multi-agent wording:

```text
Use multi-agent if needed to fix this typo.
```

Expected behavior: the manager should choose Direct mode because dispatch overhead is not justified.

Long task requiring durable coordination:

```text
Refactor checkout, update API contracts, migrate tests, and verify the UI flow. Use sub-agents and keep the work resumable.
```

Expected behavior: the manager should choose Lite or Full mode depending on risk, available tools, and verification requirements.

---

## Artifact Initialization

For Full mode, initialize a durable run:

```bash
python3 scripts/init_run.py \
  --project-root /path/to/project \
  --title "Checkout Refactor" \
  --agents frontend,backend,tests
```

This creates:

```text
/path/to/project/workspace/checkout-refactor/
├── acceptance_registry.json
├── capability_snapshot.md
├── task_spec.md
├── progress.md
├── run_state.json
├── trace.jsonl
├── evaluator_report.md
└── tasks/
    ├── 1.1-frontend.md
    ├── 1.2-backend.md
    └── 1.3-tests.md
```

---

## Report Validation

Validate generated reports before relying on them:

```bash
python3 scripts/validate_report.py <artifact-dir>/1.1-frontend-report.md --type subagent
```

Supported artifact types:

- `spec`
- `progress`
- `subagent`
- `evaluator`

When protocol files such as `acceptance_registry.json` or `run_state.json` sit next to a validated artifact, the validator also checks those files.

---

## Repository Layout

```text
multi-agent-dispatcher/
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

Detailed protocol material lives in `references/`. Runtime-specific guidance lives in `adapters/`.

---

## Runtime Adapters

The protocol is runtime-neutral. Adapters describe how to apply it in specific agent environments:

- [Codex adapter](adapters/codex.md)
- [Claude Code adapter](adapters/claude-code.md)
- [Harness protocol reference](references/harness-protocol.md)

Adapters do not change the protocol. They map the same gates, artifacts, evidence rules, and fallback behavior to the available runtime controls.

---

## Relationship To Superpowers

This project is independent and does not require Superpowers to run.

The design is influenced by [obra/superpowers](https://github.com/obra/superpowers), a software development methodology by Jesse Vincent. Multi-Agent Dispatcher adopts compatible engineering patterns such as test-first evidence, fresh-context sub-agents, review gates, worktree isolation, and verification before completion.

The project does not copy Superpowers skill bodies and does not require the Superpowers plugin. The relationship is:

```text
multi-agent-dispatcher = routing and harness authority
Superpowers-style methods = optional supporting engineering practices
```

Mode selection always runs first. Supporting methods are applied only when they fit the selected execution mode.

---

## Release History

### v5.2.2

- Rewrote the English and Chinese README files in a formal public documentation style.
- Clarified the project positioning, execution modes, installation flow, runtime package boundary, and Superpowers acknowledgement.
- No runtime protocol changes.

### v5.2.1

- Added bilingual public documentation.
- Added an explicit acknowledgement of Superpowers-inspired engineering patterns.
- Added `scripts/package_skill.py` for clean runtime-only packaging.
- Consolidated Direct, Lite, and Full routing guidance in the public README.
- Expanded evaluation coverage for TDD evidence, review separation, Superpowers interaction, and clean sharing.

### v5.0.1

- Added a right-sizing gate before capability checks and DAG creation.
- Clarified that explicit multi-agent wording authorizes evaluation, not automatic dispatch.
- Added guidance to skip workers, worktrees, and artifacts for small tasks.

### v5.0.0

- Upgraded the project from protocol guidance into a manager-enforced harness protocol.
- Added capability snapshots, `run_state.json`, `acceptance_registry.json`, and `trace.jsonl`.
- Added evaluator validation and runtime adapters for Codex and Claude Code-style environments.

### v4.0.0

- Introduced the closed-loop multi-agent protocol.
- Added artifact initialization, report validation, role boundaries, stop conditions, and evaluator templates.

---

## License

No license file is currently included in this repository.
