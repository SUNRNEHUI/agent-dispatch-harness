# Roles

Use these role boundaries when assigning multi-agent work.

## Manager

- Owns spec, DAG, artifact directory, state, merge, and final acceptance.
- Does not outsource the immediate critical-path task if the next local step depends on it.
- Reviews reports before merging and rejects unverified completion.

## Explorer

- Answers specific codebase or system questions.
- Does not edit files.
- Returns concise findings, relevant paths, and confidence level.

Use for: unfamiliar code areas, dependency mapping, identifying test commands, locating ownership boundaries.

## State Witness / Adversarial Reviewer

- Owns production-state fidelity, not implementation.
- Traces the reported user action through the real call sites that compute the decision.
- Names every gate input, producer, lifecycle, and state combination in `state_witness.md`.
- Reviews after GREEN and must try to find a real production combination missing from tests.
- Returns FAIL when a test uses a synthetic or semantically unreachable combination, even if
  the policy function passes.
- A FAIL creates a repair task and a new RED → GREEN → REFACTOR cycle.

Use for: blank/spinner/stuck UI, token/generation races, async queues, policy gates,
feature flags, lifecycle cleanup, and any bug described with multiple Boolean/enum states.

## Worker

- Implements a bounded slice.
- Has explicit file or responsibility ownership.
- Must not revert changes made by others.
- Writes a sub-agent report with commands, evidence, risks, and unverified paths.

Use for: frontend slice, backend slice, tests slice, migration slice, docs slice.

## Evaluator

- Verifies outputs against acceptance criteria.
- Does not explain away missing evidence.
- Must be allowed to return FAIL.
- Checks for stubs, TODOs, mocks, UI/browser gaps, and missing readback.

Use for: user-facing workflows, high-risk changes, release gates, broad UI changes.

## Merger

- Reads reports and diffs.
- Resolves conflicts only within authorized ownership boundaries.
- Runs the smallest sufficient integration verification.

Use only when merge work is large enough to justify a separate role.
