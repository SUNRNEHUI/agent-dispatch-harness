# TDD Gates

Use this reference when a delegated task changes code behavior, when the user
explicitly requests TDD, when a project instruction requires test-first
development, or when a manager/evaluator must accept TDD or substitute
evidence.

The report is not the source of truth by itself. Prefer wrapper-generated
trace-backed evidence: command output, fixture paths, screenshots/logs when
relevant, and a chronological `tdd_trace.jsonl` that a checker can inspect.
Use `scripts/harness_test_run.py` to run tests/checks when available, because it
captures stdout/stderr tails, exit code, timestamp, and trace events outside
the worker's narrative. Use `scripts/tdd_gate_check.py` to validate the trace.

## Evidence Chronology

TDD evidence must preserve order:

1. Gate mode selected before behavior implementation.
2. RED or gap-revealing evidence recorded before production changes.
3. Fix or implementation evidence recorded after RED.
4. GREEN verification recorded after the fix.
5. Refactor/audit verification recorded after cleanup when applicable.

Do not relabel tests-after as TDD. A test written or first run after the fix may
be useful regression verification, but it cannot satisfy `strict_tdd` or
test-first RED evidence. If chronology is missing or ambiguous, the manager
must treat the TDD gate as failed, repaired, or explicitly substituted; it must
not infer chronology from a confident summary.

When wrapper support exists, normal workers should not hand-write
`tdd_trace.jsonl`. They should run checks through `scripts/harness_test_run.py` and
reference the generated trace. Hand-written trace events are lower-trust
evidence and should be treated as advisory unless corroborated by command
output, filesystem state, or an external runner.

## Gate Levels

The dispatcher uses two separate gates. Do not collapse them into a generic "tested" claim.

### Test-First Evidence Gate

Use this by default for Lite Orchestration or Full Harness code behavior changes.

Requirements:

- identify the verification path before implementation
- add or run a failing or gap-revealing test when meaningful project tests exist or can be added at reasonable cost
- implement only after the RED or gap evidence is recorded
- run the GREEN verification after implementation
- record the command, result, evidence path or output summary, and trace event
  order

This gate is evidence-oriented. It allows a substitute check when project tests are unavailable, the change is docs/config-only, or adding a test would cost more than the behavior risk justifies.

### Strict TDD Gate

Use this when any of these are true:

- the user explicitly asks for TDD, RED/GREEN, or test-driven implementation
- a project instruction, issue, plan, or phase gate requires TDD
- the task is a bug fix or behavior change in a tested code path and the relevant test can be written before production code
- the manager assigns a worker specifically to implement from tests

Requirements:

1. Write one focused failing test for the intended behavior.
2. Run the test and confirm it fails for the expected reason, not because of syntax, imports, setup, or an unrelated error.
3. Implement the smallest production change needed to pass.
4. Run the same test and relevant surrounding tests.
5. Refactor only after GREEN, then rerun the verification affected by the refactor.

If production code was already written before the RED step in a strict TDD task, stop and repair the process. The manager decides whether to revert, isolate the already-written code, or ask the user to accept a non-TDD path. Do not relabel tests-after as TDD.

When physical file evidence is useful, run the checker with source paths:

```bash
python3 scripts/tdd_gate_check.py --source-path <changed-source-file> <artifact-dir>/tdd_trace.jsonl
```

`--source-path` enables mtime checks for strict TDD. The checker rejects a
source file whose modification time predates the RED event, and it requires a
later GREEN/REFACTOR/verification PASS. Use this only for files that belong to
the current TDD cycle; old untouched source files should not be passed as
cycle evidence.

For bug fixes, strict TDD is the default whenever a focused failing test or
reproduction can be created at reasonable cost. A bugfix report must not claim
the defect is fixed without failure evidence that predates the fix. If the bug
cannot be reproduced executably, report the work as investigation, mitigation,
or substitute-verified risk reduction rather than a verified fix.

## Substitute Verification

Use substitute verification only when Strict TDD is not required and a meaningful test-first path is unavailable or disproportionate.

Valid substitutes include:

- focused script or fixture
- CLI smoke check
- typecheck, lint, build, or schema validation
- browser interaction and screenshot for UI behavior
- API round trip, database readback, or log evidence
- diff review or markdown/link validation for docs-only work

The report must state why automated test-first evidence was not used.

Substitute boundaries:

- Substitute is valid for docs-only, config-only, analysis-only, packaging-only,
  or low-risk changes where a meaningful RED path is unavailable or
  disproportionate.
- Substitute is not a backdoor for code behavior changes that have a practical
  test path.
- Substitute cannot satisfy a strict TDD request unless the manager records the
  broken TDD path and obtains or documents the required decision.
- Substitute evidence must still be concrete and chronological: identify the
  check before editing when possible, run it after editing, and record command,
  result, and no-test reason.
- For Full Harness, include substitute events in the TDD trace so a checker or
  evaluator can distinguish an accepted substitute from missing RED evidence.

## Runtime Wrapper

Use `scripts/harness_test_run.py` when available:

```bash
python3 scripts/harness_test_run.py \
  --trace <artifact-dir>/tdd_trace.jsonl \
  --task-id 1.2 \
  --gate-mode strict_tdd \
  --reason "bugfix requires RED before implementation" \
  --phase RED \
  --run-state <artifact-dir>/run_state.json \
  --actor-id <continuation-owner-if-claimed> \
  --owner-epoch <continuation-epoch-if-claimed> \
  -- pytest path/to/test.py
```

The wrapper appends events to `tdd_trace.jsonl` and can update
`run_state.json.tdd_current_cycle_context` with the latest command, result,
exit code, stdout/stderr tails, retry count, and trace path. This current cycle
context is the lightweight failure scene to pass between manager and workers;
do not move entire workspace telemetry between agents when the failure scene is
enough.

For Full mode, the context update uses the same artifact lock and before/after digest journal
as `harnessctl`; it must not invalidate a sealed run. Once continuation ownership is active,
the wrapper checks actor ID and owner epoch before executing the command and again before
committing context. Omit these flags only while the continuation is still unclaimed.

For substitute checks, pass `--no-test-reason` so the trace records why a
test-first path was not used.

## Retry And Rollback

Each TDD cycle should have a small retry budget, normally three attempts. When
the same RED/GREEN cycle exceeds its budget, stop and record a decision point
instead of continuing silently.

After a verified GREEN in an isolated worktree, a manager may create a local
checkpoint commit to preserve the known-good state. Do not run
`git reset --hard` automatically in the main worktree. Hard rollback is allowed
only in an isolated disposable worktree or after explicit user authorization.

## Required Report Record

Every sub-agent report must include `Test-First Or Substitute Verification` with these fields:

- `Gate mode`: `strict_tdd`, `test_first_evidence`, `substitute`, or `not_applicable`
- `Applicability reason`: why this gate mode fits the task
- `RED command`
- `RED result`
- `RED failure reason`
- `GREEN command`
- `GREEN result`
- `Refactor check`
- `Substitute check`
- `No-test reason`

For `strict_tdd`, RED and GREEN fields are required evidence. For `test_first_evidence`, RED may be a gap-revealing existing test or a new failing test. For `substitute`, the substitute and no-test reason must be concrete. For `not_applicable`, the task must be docs-only, config-only, analysis-only, or otherwise not a code behavior change.

When a trace exists, the report must include the trace path and the checker
result or explain why the checker was unavailable. The Markdown report may
summarize evidence, but acceptance should rely on the trace and command outputs
for chronology-sensitive claims.

## Manager Acceptance Rules

The manager cannot accept a code behavior change when:

- the report omits the gate mode
- a strict TDD task has no RED command/result/failure reason
- a test-first task implements first and tests later without explicitly recording that the TDD path was broken
- substitute verification is used without a concrete no-test reason
- acceptance criteria do not link to the relevant TDD or substitute evidence
- trace-backed chronology is required but missing, invalid, or contradicted by
  the report

Sub-agent reports are evidence for manager acceptance. They are not final acceptance.

For risky Full Harness implementation, the evaluator report should include `Testing Gate Evidence Checked` and explicitly state whether the testing gate records were present, valid, and mapped to acceptance criteria.
