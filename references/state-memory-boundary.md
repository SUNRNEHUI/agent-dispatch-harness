# State And Memory Boundary

Use this reference when Full Harness creates or resumes durable artifacts, or
when a manager is unsure whether information belongs in task state, execution
logs, or cross-task memory.

## Core Boundary

State is run-scoped. Memory is cross-run knowledge.

Do not store long-term user preferences, reusable lessons, or project-wide
knowledge inside a single run artifact. A run artifact may record a memory
candidate, but the manager must promote it through the runtime's normal memory
or documentation process only after the task is complete and the fact is stable.

## Layers

| Layer | Lifetime | File | Purpose |
| --- | --- | --- | --- |
| Working State | Current stage or current task | `run_state.json.state_layers.working_state` | Active stage, current task, blockers, and volatile execution facts. |
| Session State | Current Full Harness run | `run_state.json.state_layers.session_state` | Shared decisions, assumptions, artifact paths, delegation state, and scoped context all agents need for this run. |
| Continuation State | Across runtime sessions within one Full run | `run_state.json.continuation` | Current fenced owner, latest checkpoint, explicit next action, pending verification, and repository snapshot used to build a resume packet. |
| Execution Log | Append-only audit trail | `trace.jsonl`, `tdd_trace.jsonl` | Immutable events for dispatch, tool evidence, state transitions, TDD chronology, verification, stops, and handoff. |
| Memory Candidates | Proposed cross-task learning | `run_state.json.state_layers.memory_boundary.memory_candidates` | Facts that might be reusable later, kept as candidates rather than committed memory. |
| Cross-Task Memory | Outside the run artifact | external memory system, project docs, or user-approved notes | Durable knowledge reused across tasks. Do not write it from Full Harness by default. |

## Write Rules

- Write changing execution status to `run_state.json`, not `task_spec.md`.
- Write human-readable progress and decisions to `progress.md`.
- Append irreversible evidence to `trace.jsonl` or `tdd_trace.jsonl`; do not rewrite trace history.
- Keep `task_spec.md` as the agreed local plan/spec. Update it when scope,
  acceptance criteria, non-goals, or constraints change.
- Keep cross-task lessons out of run artifacts unless they are explicitly marked
  as memory candidates.
- Do not promote memory candidates automatically. Promotion needs user approval,
  project documentation ownership, or a runtime memory update workflow.
- Checkpoint at verified boundaries and before likely interruption. Store the literal next
  action and unresolved verification; do not paste hidden reasoning or a chat transcript.
- A replacement runtime must recover and validate before claiming a new owner epoch. It
  reads durable artifact paths, never treats old chat availability as a prerequisite.

## Markdown vs JSON

Use Markdown for plans, rationale, and human review. Use JSON for current
machine-readable state that scripts or future agents must update predictably.

`task_spec.md` is local plan/spec, not the live task database. `run_state.json`
is the live state record. `trace.jsonl` is the append-only audit log.

## Continuation Boundary

The resume packet can reconstruct observable work state: selected run, active task, blockers,
required files, latest explicit next action, owner epoch, transaction recovery outcome, and
whether project files changed after checkpoint. It cannot reconstruct unrecorded intent,
hidden model reasoning, provider-local tool state, secret values, or a side effect already
started outside the harness. When drift exists, the receiving agent must inspect the diff
before acting; it must not infer that the recorded next action is still safe.
