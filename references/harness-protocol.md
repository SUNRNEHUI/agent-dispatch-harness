# Harness Protocol Reference

This reference defines the v7.4 core protocol. It is intentionally separate from any one agent runtime. Runtime adapters may become thinner as models improve, but the manager still needs a durable protocol for state, continuation ownership, evidence, budget, and final acceptance.

## Protocol Goal

The harness turns multi-agent orchestration from advice into a required control loop:

1. choose Direct, Lite, or Full mode
2. when the goal is fuzzy or false-completion risk is high, run Spec Synthesis before implementation dispatch
3. discover actual runtime capabilities
4. create a bounded spec and acceptance registry with pass algorithms
5. advance through explicit states
6. collect worker, testing-gate, review, and evaluator evidence
7. stop on budget or safety breaks
8. claim completion only when required acceptance records pass

Spec Synthesis details: `references/spec-synthesis.md`. Harness instance quality can be scored with `scripts/score_harness.py` (harness quality ≠ product success).

## Mode Selection Gate

Explicit multi-agent wording authorizes the manager to evaluate the mode. It does not require dispatch.

The manager should skip multi-agent orchestration when the task is small, localized, lacks clean ownership boundaries, or would cost more to coordinate than to complete directly. In that case, the manager should say so briefly, execute as a single agent, and verify normally without creating run artifacts.

The manager should proceed with Lite Orchestration or Full Harness when delegation materially helps because the work is parallelizable, long, resumable, risky, evaluator-sensitive, or benefits from isolated ownership and rollback.

Other planning, TDD, worktree, review, verification, or parallel-agent methods are supporting methods after this gate. They do not replace mode selection.

## Operating Modes

Choose the thinnest mode that still protects the work.

### Direct Mode

Use Direct mode for small edits, narrow fixes, simple questions, direct commands, and ordinary single-agent work. The manager does the work directly, verifies normally, and does not create harness artifacts, worker reports, trace files, or registries.

### Lite Orchestration

Use Lite Orchestration for medium tasks where decomposition helps but the cost of a full harness would dominate the work. Lite mode may use a short plan, bounded worker or stage reports, and only the acceptance evidence needed for the task. It should not create the full artifact set by default.

Lite mode is appropriate when:

- the task has two or more bounded surfaces, but is not long-running or high-risk
- the user asked for coordination, but resumability is not important
- a worker-style split helps review without needing durable machine-readable state
- verification can be captured in a small command summary, diff review, screenshot, or report

Lite mode may borrow test-first evidence, strict TDD, compact review, or parallel-agent discipline when useful, but it should not expand into full ceremony without a Full Harness trigger.

### Full Harness

Use Full Harness only when the work is long, risky, resumable, multi-stage, evaluator-sensitive, likely to need rollback, or explicitly requires durable coordination across agents or sessions.

Full Harness is the only mode that requires the complete record set below. If a task does not need resumable state, acceptance registry blocking, budget breakers, and trace continuity, prefer Direct or Lite mode.

## Required Records

Required records are mandatory only for Full Harness runs. Direct mode creates none. Lite Orchestration may keep only a short plan, worker report, and necessary acceptance evidence.

A Full Harness run should preserve these records in durable files when the task is complex or resumable.

The runtime schema version is defined once in `scripts/harness_schema.py`. Templates,
initialization, validation, and guarded transitions must use that source. A mismatched or
missing version is an integrity failure, not a hint to guess a migration.

### Capability Record

- runtime name
- available tools
- unavailable tools
- available supporting methods such as TDD, worktree, review, verification, or parallel-agent skills
- filesystem and sandbox limits
- browser or UI verification availability
- sub-agent mechanism or fallback
- worktree support
- external dependencies and credentials
- chosen fallback for missing capabilities

### State Record

- current state
- previous state
- transition reason
- owner
- timestamp or ordering marker
- evidence path
- next action

### Continuation Record

The additive `continuation` record is independent of the top-level run lifecycle. A
mid-run runtime switch does not move the run to terminal `HANDED_OFF`.

- protocol and status: `unclaimed`, `active`, or `ready`;
- current owner actor ID, runtime, monotonically increasing epoch, and claim time;
- previous owner and takeover count;
- latest checkpoint ID/sequence, current task, literal next action, pending verification,
  and repository snapshot;
- last resume actor/runtime/reason and whether the takeover was forced.

The owner epoch is a fencing token, not metadata. Once a run is claimed, all state-changing
controller calls must match both actor ID and epoch. A later session may reuse an actor name,
but a stale process holding an earlier epoch still cannot write.

### Model Route Record

- runtime identity established by the active adapter, not executable discovery alone
- profile: `fast`, `main`, `planner`, or `critical_reviewer`
- requested model and reasoning effort
- resolved model when the runtime exposes it
- observable route reason
- escalation count

Density selection happens first. A cheap model is not a reason to dispatch, and a requested
model is not evidence that the runtime resolved it. Runtime-specific mappings live in
`references/model-routing.md` and the matching adapter.

### Production State Witness Record

For state/UI/async/concurrency behavior, Full Harness must retain a `state_witness.md`
record before implementation. It contains:

- symptom and terminal user-facing condition;
- exact production call chain and decision function;
- state inputs with their producers and lifecycle;
- truth table for failing, fixed, and preserved-blocking combinations;
- executable test/fixture mapping for critical rows;
- unknowns, logging added, and verification tier reached.

The manager must run an adversarial call-site review after GREEN. A missing or unreachable
row is a review FAIL and requires a new TDD cycle; it cannot be waived by a passing unit test.

### Acceptance Record

- criterion
- owner
- required evidence
- status: `pending`, `pass`, `fail`, `blocked`, or `scoped_out`
- evidence path or command summary
- verification gate mode: `strict_tdd`, `test_first_evidence`, `substitute`, or `not_applicable`
- RED/GREEN evidence or substitute verification evidence for code behavior changes when applicable
- spec compliance or code quality review evidence when required by risk
- production-state witness and adversarial review evidence when stateful behavior is in scope
- evaluator notes when relevant

### Testing Gate Record

For every implementation task, record the selected gate mode:

- `strict_tdd`: required when the user, project instructions, phase gate, or task assignment explicitly requires TDD. Requires RED command/result/failure reason before production code, GREEN command/result after implementation, and a refactor check after cleanup.
- `test_first_evidence`: default for Lite or Full code behavior changes when meaningful tests exist or can be added at reasonable cost. Requires failing or gap-revealing evidence before implementation and passing verification after.
- `substitute`: allowed only when meaningful test-first evidence is unavailable or disproportionate. Requires no-test reason and substitute check.
- `not_applicable`: allowed only for docs-only, config-only, analysis-only, or non-behavior work.

Worker reports and acceptance records should carry the same gate mode. A report that omits the gate mode is not acceptable evidence for code behavior changes.

### Budget Record

- stage budget
- observed usage
- breaker condition
- stop reason
- continuation decision

### Trace Record

- capability gate result
- dispatch decisions
- report paths
- evaluator result
- commands or checks that matter for acceptance
- final registry status

Trace files are JSONL: every non-empty line must be one JSON object. Examples do not belong
in runtime trace templates. A started state transaction without a matching committed event
is an incomplete transition and blocks resume or acceptance.

## Controlled Runtime Operations

After `init_run.py --mode full`, use the narrow control surface instead of hand-editing live
run, task, or acceptance statuses:

```bash
python3 <skill-dir>/scripts/harnessctl.py discover <project-root>
python3 <skill-dir>/scripts/harnessctl.py resume <project-root> --runtime grok --actor-id <unique-session-id> --takeover-reason "previous runtime interrupted"
python3 <skill-dir>/scripts/harnessctl.py checkpoint <project-root> --runtime grok --actor-id <actor> --owner-epoch <epoch> --current-task 1.1 --next-action "run focused tests" --reason "verified boundary"
python3 <skill-dir>/scripts/harnessctl.py handoff <project-root> --actor-id <actor> --owner-epoch <epoch> --next-action "run focused tests" --reason "clean runtime switch"
python3 <skill-dir>/scripts/harnessctl.py validate <artifact-dir>
python3 <skill-dir>/scripts/harnessctl.py seal <artifact-dir> --reason "reviewed synthesis baseline"
python3 <skill-dir>/scripts/harnessctl.py dispatch-create <artifact-dir> --worker-id <runtime-worker-id> --task-id 1.1 --contract-path tasks/1.1-worker.md --report-path 1.1-worker-report.md --runtime codex --profile main --requested-model gpt-5.6-luna --reasoning-effort xhigh --route-reason "default high-frequency manager"
python3 <skill-dir>/scripts/harnessctl.py dispatch-update <artifact-dir> --dispatch-id <id> --status reported
python3 <skill-dir>/scripts/harnessctl.py task-set <artifact-dir> --task-id 1.1 --status ready
python3 <skill-dir>/scripts/harnessctl.py task-set <artifact-dir> --task-id 1.1 --status running
python3 <skill-dir>/scripts/harnessctl.py task-set <artifact-dir> --task-id 1.1 --status passed --evidence-file <artifact-relative-report-or-log> --no-test-reason <reason-if-not-applicable>
python3 <skill-dir>/scripts/harnessctl.py acceptance-set <artifact-dir> --criterion-id AC-001 --status pass --evidence-file <artifact-relative-report-or-log> --pass-algorithm <rule> --no-test-reason <reason-if-not-applicable>
# Advance the legal run sequence; do not jump directly from intake to accepted.
python3 <skill-dir>/scripts/harnessctl.py run-set <artifact-dir> --status gated
python3 <skill-dir>/scripts/harnessctl.py run-set <artifact-dir> --status specified
# ... dispatched -> reported -> evaluating ...
python3 <skill-dir>/scripts/harnessctl.py run-set <artifact-dir> --status accepted --evidence-file <final-verification-report>
python3 <skill-dir>/scripts/harnessctl.py recover <artifact-dir>
```

`resume` is the replacement runtime entry gate. From a project root it discovers exactly
one non-terminal Full run, takes a coordination lock, recovers incomplete journal entries,
validates all canonical state and evidence chains, then commits a new owner epoch and emits
a resume packet. Zero active runs, multiple active runs, corrupt state, or failed recovery
leaves ownership unchanged. Terminal runs are never auto-selected.

The packet includes artifact/project paths, active tasks, blockers, required reads, recorded
next action, pending verification, current/previous owner, and repository drift. A content
fingerprint distinguishes pre-existing dirty work from changes made after checkpoint. The
harness-owned `workspace/**` artifact is excluded from this project drift calculation.

After claim, append `--actor-id <packet owner.actor_id> --owner-epoch <packet owner.epoch>`
to every mutating command shown above. Read-only `discover`, `validate`, and `status.py` do
not require ownership.

The controller validates the current and candidate documents, rejects illegal transitions
or unverified PASS states, writes state atomically under an artifact lock, and journals
started/committed transaction events. `validate` also rejects malformed JSONL, empty
acceptance registries, schema drift, incomplete transactions, unresolved terminal tasks/stages,
chat-only dispatches, canonical-state digest drift, evidence receipt/digest mismatch, and invalid active TDD traces. Journal records carry before/after digests; `recover` appends a
committed or aborted terminal event only when the canonical state matches one of those digests.

`seal` is the explicit pre-dispatch boundary for reviewed human-authored state. It is allowed only before execution and does not make prose correct; it records that the manager intentionally accepts the current structured baseline. New Full runs treat free-form `--evidence` as non-qualifying legacy context. `--evidence-file` hashes a non-empty artifact file and binds that receipt to the committed transition; a worker report still needs manager review and the relevant testing/evaluator gate.

Cross-runtime continuation transfers durable, explicit state only. It does not transfer
hidden chain-of-thought, provider-internal chat/session state, credentials, or an in-flight
external side effect. No provider quota callback is assumed: automatic takeover begins when
the replacement runtime is launched and executes `resume`.

Before dispatch, validate human-authored Full specs semantically:

```bash
python3 <skill-dir>/scripts/validate_report.py <artifact-dir>/task_spec.md --type spec --require-filled
```

For stateful behavior, validate the witness before sealing or dispatching:

```bash
python3 <skill-dir>/scripts/state_witness_check.py <artifact-dir>/state_witness.md --require-filled
```

The validator accepts explicit localized aliases and structural numbering, but rejects empty,
placeholder-only, heading-echo, generic completion-word, duplicate, or fenced-example sections. Template shape alone is never
acceptance evidence.

## State Machine

Use these states as the default harness model:

```text
INTAKE
GATED
SPECIFIED
DISPATCHED
REPORTED
EVALUATING
ACCEPTED
HANDED_OFF
```

Stop states:

```text
BLOCKED
NEEDS_DECISION
FAILED
```

The manager may use fewer states for a small delegated task, but it must not skip the gate, acceptance, and final verification semantics.

## Completion Rule

The manager can say the task is complete only when:

- required capability fallbacks are recorded
- every required acceptance record is `pass` or explicitly `scoped_out` by user decision
- required testing gate evidence has been reviewed, including RED/GREEN or substitute fields when applicable
- required spec compliance and code quality reviews are `pass` or explicitly scoped out by user decision
- required state witness and adversarial review are `pass` for stateful behavior
- user-visible acceptance is not closed by policy-only evidence; flow/device/browser evidence or an explicit blocked boundary is recorded
- evaluator `FAIL` has been resolved or explicitly scoped out by user decision
- budget breakers are closed with a continuation or stop decision
- trace points to the evidence used for completion

Worker success is not completion. A worker report is input to acceptance, not the acceptance decision itself.

## What Gets Thinner As Models Improve

These layers can shrink over time because stronger models can infer or execute them with less scaffolding:

- verbose prompt wording
- role descriptions repeated in every task
- manual checklists for obvious file ownership
- adapter-specific reminders about basic tool use
- large chat summaries when durable trace exists
- evaluator rubrics for low-risk, narrow edits

The direction is thinner instructions, not weaker guarantees.

## What Remains Long-Term

These layers should remain even with stronger models:

- capability gate: the runtime environment can change independently of the model
- state machine: long tasks need resumable state
- acceptance registry: completion needs evidence tied to criteria
- budget circuit breaker: cost, time, context, and retries remain finite
- trace: future agents need to know what happened and why
- stop conditions: destructive or high-impact operations still need explicit control
- runtime adapters: harness controls differ across products and local setups

## Adapter Contract

Each runtime adapter should answer:

- where persistent instructions live
- how capabilities are discovered
- how filesystem, sandbox, and network limits are represented
- how worktree or file ownership can be enforced
- how browser verification is performed or marked unavailable
- how sub-agents are launched, simulated, or replaced by sequential stages
- how hooks or local instructions preserve the protocol
- where trace and acceptance records should be written

Adapters must avoid claiming unavailable features. Missing controls should become fallbacks or stop conditions.
