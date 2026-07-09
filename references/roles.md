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
- Runs an independent completion-confidence check: compare the proposed final claim against the freshest evidence, name evidence gaps, and return `high`, `medium`, `low`, or `blocked` confidence.
- Treats worker self-assessment, stale evidence, missing browser/readback checks, stubs, TODOs, mocks, and unverified critical paths as confidence reducers.
- Must not force Direct or Lite work into Full Harness ceremony; use the evidence available for the selected mode unless the risk itself justifies escalation.

Use for: user-facing workflows, high-risk changes, release gates, broad UI changes.

## Merger

- Reads reports and diffs.
- Resolves conflicts only within authorized ownership boundaries.
- Runs the smallest sufficient integration verification.

Use only when merge work is large enough to justify a separate role.
