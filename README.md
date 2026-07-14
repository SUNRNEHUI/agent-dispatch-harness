# Agent Dispatch Harness

[简体中文](README.zh-CN.md) | English

Agent Dispatch Harness (formerly Multi-Agent Dispatcher) is a **runtime-agnostic task OS** for coding agents. It helps any model (Codex, Claude Code, Grok, and similar) choose the lightest process that still makes false completion hard: from one-shot Direct fixes to durable Full harness runs with evidence gates.

Current version: **v6.0.0** · 2026-07-14

---

## Overview

This skill is not “always multi-agent” and not “always write a big harness”. It is a proportional execution methodology:

```text
User intent → density decision → (optional) Spec Synthesis → execute → evidence → done
```

Multi-agent wording authorizes evaluation of dispatch. It does not force workers. Fuzzy goals should be compiled into success / fake-success / accept rules before implementation. Long, risky, or resumable work can use durable Full harness artifacts.

The manager remains responsible for:

- density / mode selection (Direct, Lite, Full)
- Spec Synthesis when success is underspecified
- scope, non-goals, ownership, and verification requirements
- assigning bounded work to sub-agents only when ownership is clean
- merging results and resolving conflicts
- re-checking critical evidence before claiming completion

Sub-agents execute bounded slices only. They never own final acceptance.

---

## Core Capabilities

- **Density decision:** stop at the lightest mode that controls false completion (Direct → synthesis → Lite → Full).
- **Spec Synthesis:** compile fuzzy or improvement-shaped goals into executable contracts before coding.
- **Selective delegation:** spawn workers only with clean ownership and real coordination benefit.
- **Durable Full harness:** `run_state`, acceptance registry, traces, and task contracts under `workspace/<slug>/`.
- **Runtime TDD evidence:** strict TDD, test-first evidence, substitute verification, and non-applicable gates with wrapper-generated traces.
- **Evidence-based acceptance:** tests, builds, logs, browser checks, screenshots, CI, or evaluator reports — never self-report alone.
- **Plan quality scoring (optional):** `scripts/score_harness.py` rates harness completeness; it is never product acceptance.
- **Runtime adapters:** Codex, Claude Code, and a universal adapter for other agents.
- **Clean packaging:** runtime-only install package without docs, caches, or private configuration.

---

## Execution Modes

| Mode | Use When | Write on disk? | Behavior |
| --- | --- | --- | --- |
| **Direct** | Tiny, clear, low fake-success risk (typo, one file, obvious fix). | No | Manager implements and verifies. No harness files. |
| **Direct+** | Clear 2–5 step work with one owner. | Chat-only plan optional | Still no Full `workspace/` tree. |
| **Lite** | Medium work with clean parallel ownership. | Short plan / compact reports | Bounded workers; no full registry by default. |
| **Full** | Long, risky, resumable, multi-session, evaluator-heavy, or worktree isolation. | `workspace/<slug>/` | Durable state, acceptance registry, traces, TDD gates. |

**Spec Synthesis** is not a fourth mode: it runs first when the goal is fuzzy, improvement-shaped, or easy to fake-complete. Compact synthesis lives in chat or a short note; Full synthesis seeds stage `0.1` via `init_run.py --with-synthesis`.

Hard rules:

- Multi-agent words ≠ must dispatch.
- Single owner + medium steps → Direct+ (chat plan), not Lite theater.
- Fuzzy goal ≠ Full harness by default.
- Improvement-shaped work needs a terminal metric and baseline plan before “optimize”.

---

## When To Use

Prefer this skill when the task involves:

- multi-agent / sub-agents / DAG / worktree / 分头处理
- fuzzy goals that need Spec Synthesis (“faster”, “better”, “more professional”)
- long, resumable, evidence-verified coordination
- deciding how much process to apply without wasting tokens

Do not force Full harness or workers for small clear work. If multi-agent is not authorized and not useful, stay single-agent.

---

## Operating Flow

```text
Context Intake
-> Density decision: Direct / synthesis / Lite / Full
-> Optional Spec Synthesis (success, fake-success, accept rules)
-> Execute selected mode
   Direct: implement, verify, report
   Lite: coordinate bounded slices, verify, report
   Full: capability, artifacts, DAG, workers, TDD gates, evaluator
-> Manager re-verify critical evidence
-> Merge / Handoff
```

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
git clone https://github.com/SUNRNEHUI/agent-dispatch-harness.git
cd agent-dispatch-harness
```

Create a clean runtime package:

```bash
python3 scripts/sync_version.py
python3 scripts/package_skill.py --verify-source
python3 scripts/package_skill.py --output /tmp/agent-dispatch-harness-runtime --force
```

Install the runtime package into Codex:

```bash
mkdir -p ~/.codex/skills/agent-dispatch-harness
rsync -a --delete /tmp/agent-dispatch-harness-runtime/ ~/.codex/skills/agent-dispatch-harness/
python3 scripts/package_skill.py --check ~/.codex/skills/agent-dispatch-harness
```

The runtime package contains only the files needed by the skill at execution time.

Runtime coordination uses a cooperative manager-only state/trace API guard, atomic JSON replacement, locked JSONL appends, and workspace identity read independently from git. This guard can be bypassed by a same-user process writing files directly; isolation depends on native sandbox/OS permissions. Verification defaults to 1800 seconds and requires timeout <= runtime budget.

---

## Migration From Earlier Names

Earlier releases used `multi-agent-dispatcher` as the public package name, and some local installs used `multi-agent-orchestrator` as the Codex skill directory. New installs should use `agent-dispatch-harness`.

When upgrading an existing local install, install the new runtime directory first, then remove old local runtime folders if they are still present and no longer needed:

```bash
rm -rf ~/.codex/skills/multi-agent-dispatcher ~/.codex/skills/multi-agent-orchestrator
```

This avoids duplicate skill entries that describe the same workflow.

---

## Runtime Package Contents

The runtime package includes:

- `VERSION`, `SKILL.md`, `master-prompt.md`, `sub-prompt.md`, `agents/openai.yaml`
- `adapters/` — `codex.md`, `claude-code.md`, `universal.md`
- `references/` — protocol, lanes, Spec Synthesis, proportionality, TDD gates, examples
- `templates/` — Full and Lite harness templates
- `scripts/` — `init_run.py`, `harness_test_run.py`, `runtime_state.py`, `validate_workspace.py`,
  `status.py`, `tdd_gate_check.py`, `validate_report.py`, `score_harness.py`, `score_skill_protocol.py`

The authoritative file list is `scripts/package_skill.py:RUNTIME_FILES`.

It intentionally excludes:

- `README.md`
- `README.zh-CN.md`
- `scripts/sync_version.py`
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
├── tdd_trace.jsonl
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

For TDD-sensitive work, validate the dedicated TDD trace:

```bash
python3 scripts/tdd_gate_check.py <artifact-dir>/tdd_trace.jsonl
```

The checker validates chronology for strict TDD, accepts test-first gap evidence when recorded, and rejects missing substitute reasons.

Use the test wrapper when available so trace events are generated by the runtime command runner rather than hand-written by an agent:

```bash
python3 scripts/harness_test_run.py \
  --trace <artifact-dir>/tdd_trace.jsonl \
  --task-id 1.1 \
  --gate-mode strict_tdd \
  --phase RED \
  --run-state <artifact-dir>/run_state.json \
  -- pytest path/to/test.py
```

For strict TDD cycles, `tdd_gate_check.py --source-path <file>` can add filesystem mtime checks for the files changed in that cycle.

---

## Repository Layout

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

The design is influenced by [obra/superpowers](https://github.com/obra/superpowers), a software development methodology by Jesse Vincent. Agent Dispatch Harness adopts compatible engineering patterns such as test-first evidence, fresh-context sub-agents, review gates, worktree isolation, and verification before completion.

The project does not copy Superpowers skill bodies and does not require the Superpowers plugin. The relationship is:

```text
agent-dispatch-harness = routing and harness authority
Superpowers-style methods = optional supporting engineering practices
```

Mode selection always runs first. Supporting methods are applied only when they fit the selected execution mode.

---

## Version management

Single source of truth:

```bash
# VERSION file holds MAJOR.MINOR.PATCH (no leading v)
cat VERSION

# Rewrite README / SKILL current-version lines from VERSION
python3 scripts/sync_version.py --fix --date 2026-07-14

# Verify only
python3 scripts/sync_version.py

# Package and check install
python3 scripts/package_skill.py --verify-source
python3 scripts/package_skill.py --output /tmp/agent-dispatch-harness-runtime --force
python3 scripts/package_skill.py --check /tmp/agent-dispatch-harness-runtime
```

Release checklist:

1. Bump `VERSION`.
2. Run `sync_version.py --fix --date <YYYY-MM-DD>`.
3. Update bilingual release notes in this README and `README.zh-CN.md`.
4. Run `python3 scripts/test_runtime_behavior.py` and `python3 scripts/score_skill_protocol.py` (if available).
5. Commit on a `release/vX.Y.Z` branch, open PR or merge to `main`, tag `vX.Y.Z`, publish GitHub Release.

---

## Release History

### v6.0.0

- Repositioned the skill as a **universal task OS**: proportional density (Direct / Lite / Full), not multi-agent-first.
- Added **Spec Synthesis** for fuzzy and improvement-shaped goals (`references/spec-synthesis.md`, `init_run.py --with-synthesis`).
- Added proportionality and progressive-load guidance (`references/proportionality.md`, shorter `SKILL.md` / prompts).
- Added universal runtime adapter and optional harness quality scoring (`adapters/universal.md`, `scripts/score_harness.py`, `scripts/score_skill_protocol.py`).
- Hardened acceptance language: manager re-verify required; `score_harness` is never product PASS.
- Preserved mainline runtime safety: cooperative manager state/trace API, atomic JSON, locked JSONL, timeout budgets, workspace binding checks.
- Public README rewritten for the v6 positioning; version management documented.

### v5.11.0

- Streamlined orchestration and added a stricter completion confidence gate (tagged release; see GitHub Releases).

### v5.10.0

- GPT-5.6-aware dispatch routing notes (tagged release; see GitHub Releases).

### v5.9.0

- Added a proportional Completion Confidence Loop to check final claims against fresh evidence before handoff.
- Expanded Verification and Evaluator guidance to expose missing checks, stale evidence, stubs, TODOs, mocks, and unverified critical paths.
- Enhanced `scripts/status.py` with task completion, acceptance rollup, evidence-gap detection, confidence bands, and next-verification guidance.
- Added lightweight confidence and evidence-gap prompts to the progress ledger and Lite plan templates.
- Preserved right-sized execution: Direct remains artifact-free, Lite remains compact, and Full remains the durable protocol for high-risk or resumable work.
- Added no new artifact type.

### v5.8.0

- Added `VERSION` plus `scripts/sync_version.py` so current-version references can be checked or updated from one source.
- Added runtime package checks with `scripts/package_skill.py --verify-source` and `--check <install-dir>`.
- Added Lite Orchestration artifacts through `templates/lite_plan.md`, `templates/lite_review.md`, and `init_run.py --mode lite`.
- Kept `progress.md` lightweight and added `scripts/status.py` for a generated single-screen summary from `run_state.json`.
- Added validator support for `lite_plan`, `lite_review`, and Lite `run_state.json`, plus runtime behavior tests.
- Kept automated mode-router evaluation out of this release; `references/eval_cases.md` remains the human-readable regression set.

### v5.7.0

- Added an explicit State and Memory boundary for Full Harness runs.
- Clarified that `task_spec.md` is the local human-readable plan/spec, while `run_state.json` is the machine-readable live state.
- Added `state_layers` for Working State, Session State, Execution Log, and Memory Boundary.
- Added `references/state-memory-boundary.md` and included it in runtime packaging.
- Updated validation to require the core `state_layers` structure in `run_state.json`.

### v5.6.0

- Renamed the public project and runtime skill from Multi-Agent Dispatcher to Agent Dispatch Harness.
- Updated repository URLs, install paths, runtime metadata, and bilingual documentation for the new name.
- Renamed the TDD command wrapper to `scripts/harness_test_run.py` and updated trace `source` values.
- Added migration guidance for older `multi-agent-dispatcher` and `multi-agent-orchestrator` local installs.
- Preserved the Direct, Lite, and Full mode model, with Full Harness remaining the durable advanced execution protocol.

### v5.5.0

- Added wrapper-generated TDD trace support for verification commands, now exposed as `scripts/harness_test_run.py`.
- Extended `scripts/tdd_gate_check.py` with optional `--source-path` mtime checks for strict TDD cycles.
- Added `tdd_current_cycle_context` to run-state templates and initialization output.
- Clarified that normal workers should prefer wrapper-generated trace evidence over hand-written TDD traces.
- Added retry, checkpoint, and rollback guidance to Bugfix and Feature-Spec lanes without allowing automatic `git reset --hard` in the main worktree.

### v5.4.0

- Added Bugfix Lane and Feature-Spec Lane references for task-type-specific development flow.
- Added `templates/tdd_trace.jsonl` and `scripts/tdd_gate_check.py` for runtime-neutral TDD chronology validation.
- Updated run initialization and runtime packaging so TDD trace artifacts and checker scripts are included.
- Tightened sub-agent and evaluator templates to require trace path, chronology summary, first production edit, and unverified critical path fields.
- Expanded evaluation cases for code-before-RED, passing-test-as-RED, shell-bypass, UI-only-unit-test, self-report-only, and missing no-test-reason failures.
- Added `.gitignore` protection for generated workspaces, worktrees, and Python cache files.

### v5.3.0

- Added a two-level testing model: `Test-First Evidence Gate` and `Strict TDD Gate`.
- Added `references/tdd-gates.md` for RED/GREEN, substitute verification, and manager acceptance rules.
- Added required `Test-First Or Substitute Verification` fields to sub-agent reports.
- Extended protocol JSON records with `verification_gate`.
- Updated validation so sub-agent reports and protocol records cannot omit the testing gate structure.

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
