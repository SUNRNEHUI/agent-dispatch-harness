# Superpowers Integration

This skill can borrow mature methods from Superpowers-style workflows, but it remains the routing authority for multi-agent requests.

## Acknowledgement

This project is independent and does not require Superpowers to run. Its design intentionally borrows several engineering patterns inspired by [obra/superpowers](https://github.com/obra/superpowers), including test-first evidence, fresh-context subagents, review gates, worktree isolation, and verification-before-completion.

Superpowers is a complete software development methodology by Jesse Vincent. This project does not copy Superpowers skill bodies or require its plugin; it adapts compatible ideas into a smaller multi-agent routing harness.

## Principle

Use `agent-dispatch-harness` to choose Direct Mode, Lite Orchestration, or Full Harness first. Use Superpowers-style methods only after the selected mode justifies them.

Do not treat another planning, TDD, worktree, review, verification, or parallel-agent workflow as a competing top-level router.

## Method Mapping

| Method | Use In | Purpose |
| --- | --- | --- |
| Parallel-agent discipline | Lite / Full | Dispatch only independent problem domains with clean ownership and no unresolved sequential dependency. |
| Fresh worker context | Lite / Full | Give each worker task-local instructions instead of relying on hidden manager context. |
| Test-first evidence | Lite / Full code behavior changes | Prefer RED/GREEN evidence when meaningful tests exist or can be added at reasonable cost. |
| Strict TDD gate | Explicit TDD requests, project TDD rules, tested bug fixes | Require RED before production code, GREEN after implementation, and a refactor check. |
| Spec compliance review | Full, or risky Lite | Check whether the implementation matches acceptance criteria, non-goals, and scope. |
| Code quality review | Full, or risky Lite | Check maintainability, project conventions, error handling, and regression risk. |
| Verification before completion | All modes | Make final claims only after reading current evidence and stating unverified paths. |
| Worktree isolation | Full, or conflict-prone Lite | Isolate independent code changes when repository state and branch policy allow it. |
| Skill pressure cases | Skill maintenance | Test trigger, routing, delegation, and acceptance behavior with eval cases before release. |

## Mode Rules

### Direct Mode

Do not escalate a small task just because Superpowers-style methods exist. Use the project's ordinary verification path and finish directly.

### Lite Orchestration

Use lightweight borrowing:

- split only cleanly independent scopes
- assign disjoint file or responsibility ownership
- ask for compact reports or inline evidence
- use test-first evidence when the task changes code behavior and a meaningful test path exists
- use strict TDD only when the user, project, or worker assignment requires it
- avoid full implementer/reviewer loops unless risk justifies them

### Full Harness

Use stronger borrowing:

- require capability and ownership records
- require an explicit testing gate mode for implementation tasks: `strict_tdd`, `test_first_evidence`, `substitute`, or `not_applicable`
- require RED/GREEN or substitute verification evidence for code behavior changes
- use spec compliance and code quality review as separate checks when implementation risk is material
- keep review results and verification evidence tied to acceptance criteria
- stop or repair on FAIL/BLOCKED instead of summarizing around it

## What Not To Copy

Do not copy whole Superpowers skill bodies into this project. Avoid tool-specific paths, long examples, absolute claims that ignore project context, and heavy review/TDD ceremony for docs-only, config-only, small, or exploratory tasks.

The reusable value is the control mechanism: independent task boundaries, fresh context, test-first evidence, separate review concerns, and evidence before claims.
