# TDD Gates

Use this reference when a delegated task changes code behavior, when the user explicitly requests TDD, or when a project instruction requires test-first development.

## Gate Levels

The dispatcher uses two separate gates. Do not collapse them into a generic "tested" claim.

### Test-First Evidence Gate

Use this by default for Lite Orchestration or Full Harness code behavior changes.

Requirements:

- identify the verification path before implementation
- add or run a failing or gap-revealing test when meaningful project tests exist or can be added at reasonable cost
- implement only after the RED or gap evidence is recorded
- run the GREEN verification after implementation
- record the command, result, and evidence path or output summary

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

## Manager Acceptance Rules

The manager cannot accept a code behavior change when:

- the report omits the gate mode
- a strict TDD task has no RED command/result/failure reason
- a test-first task implements first and tests later without explicitly recording that the TDD path was broken
- substitute verification is used without a concrete no-test reason
- acceptance criteria do not link to the relevant TDD or substitute evidence

Sub-agent reports are evidence for manager acceptance. They are not final acceptance.

For risky Full Harness implementation, the evaluator report should include `Testing Gate Evidence Checked` and explicitly state whether the testing gate records were present, valid, and mapped to acceptance criteria.
