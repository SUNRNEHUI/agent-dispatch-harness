# Feature-Spec Lane

Use this lane for planned behavior changes where requirements, acceptance
criteria, or user-visible workflows need to be specified before implementation.

## Flow

```text
Spec -> optional worktree/isolation -> task-level TDD -> review gates -> E2E/program verification
```

## 1. Spec

- Write or update the task spec before implementation.
- Capture goal, non-goals, constraints, acceptance criteria, verification
  evidence, ownership, risks, and stop conditions.
- Decide whether Direct Mode, Lite Orchestration, or Full Harness is still the
  right mode. Escalate to Full Harness when the feature is multi-stage,
  resumable, high-risk, or requires durable acceptance tracking.
- Map each acceptance criterion to expected test-first, substitute, review, or
  E2E evidence.

## 2. Optional Worktree Or Isolation

- Use a worktree, branch, copy, or bounded file ownership when parallel work or
  merge risk justifies isolation.
- Do not create isolation just for ceremony on small or single-file changes.
- Record the isolation path and rollback plan when used.

## 3. Task-Level TDD

- Split the feature into task-level implementation slices with their own gate
  mode: `strict_tdd`, `test_first_evidence`, `substitute`, or `not_applicable`.
- For code behavior slices, identify the RED path before changing production
  code and record trace-backed evidence.
- Keep substitute verification narrow. It can cover docs/config/analysis-only
  slices or cases where meaningful test-first evidence is unavailable or
  disproportionate, but it cannot hide missing behavior tests for critical
  feature work.
- Use a TDD trace for delegated or Full Harness work. Start from
  `templates/tdd_trace.jsonl` when available and validate with
  `scripts/tdd_gate_check.py` before acceptance.
- Prefer `scripts/harness_test_run.py` for RED/GREEN commands so trace events are
  wrapper-generated. When validating physical chronology, pass changed source
  files to `scripts/tdd_gate_check.py --source-path <file>`.

## 4. Review Gates

- Separate spec compliance review from code quality review when risk justifies
  it.
- Spec compliance review checks acceptance criteria, non-goals, scope control,
  missing requirements, and accidental extra behavior.
- Code quality review checks maintainability, project conventions, imports,
  error handling, edge cases, and regression risk.
- Any `FAIL` or `BLOCKED` review must produce a repair task, stop reason, or
  explicit user decision before the feature can advance.

## 5. E2E Or Program Verification

- Run the smallest end-to-end, integration, browser, CLI, build, or program
  verification that proves the feature works in the target runtime.
- Tie verification results back to the spec acceptance criteria instead of
  reporting a generic "tests passed" claim.
- Record commands, outputs, trace paths, screenshots, logs, or other durable
  evidence that a manager or evaluator can inspect.

## Retry, Checkpoint, And Rollback

- Give each task-level TDD cycle a retry budget, normally three attempts.
- Keep `run_state.json.tdd_current_cycle_context` focused on the current
  failing command, stdout/stderr tails, trace path, and retry count.
- In isolated worktrees, create local checkpoint commits after verified GREEN
  states when later refactors may destabilize the branch.
- Do not default to `git reset --hard` in the main worktree. Record the rollback
  command and require explicit authorization unless the worktree is disposable
  and isolated.

## Done Criteria

The feature lane is complete only when:

- Each behavior slice has valid RED/GREEN or accepted substitute evidence.
- Review gates are pass, scoped out with reason, or converted into tracked
  repair work.
- E2E/program verification covers the user-facing outcome or explicitly lists
  what remains unverified.
- Acceptance criteria are mapped to current evidence and contain no unresolved
  `fail` or blocking item.
