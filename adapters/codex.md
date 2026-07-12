# Codex Runtime Adapter

This adapter maps the v5 harness protocol onto Codex-style runtimes. It is not a feature comparison; it is a checklist of practical control points the manager must use or explicitly mark unavailable.

## Persistent Instructions

Use the most specific instruction source available:

- user-level and workspace `AGENTS.md`
- project-level `AGENTS.md`
- installed skills and their references
- task-specific artifacts under the active project

Project rules override broader rules when they conflict. The manager should read the relevant files before editing and record any protocol-relevant constraints in the trace.

## Mode Selection Gate

In Codex, skill loading and actual dispatch are separate decisions. If the user mentions multi-agent work for a tiny edit, use the skill to decide that dispatch is unnecessary, then complete the task directly. Do not spawn workers, create worktrees, or initialize artifact directories unless delegation is justified.

Do not default to subagents, worktrees, or full artifact initialization merely because Codex makes local file edits, shell checks, and parallel worker prompts easy to operate. Medium tasks should normally use Lite Orchestration: a short plan, bounded worker or stage reports when useful, and targeted acceptance evidence. Escalate to Full Harness only for resumable, high-risk, multi-stage, evaluator-sensitive, or rollback-heavy work.

## Capability Gate

Record the actual session capabilities before dispatch:

- writable paths and explicit user write limits
- shell availability and sandbox policy
- network availability
- browser or app automation tools
- image, document, spreadsheet, or other specialized tools if relevant
- whether real sub-agent delegation exists in the active environment
- whether supporting skills or methods are available for TDD, worktrees, systematic debugging, code review, verification, or parallel-agent discipline
- whether worktrees are safe given current git status

If real sub-agents are unavailable, run sequential worker stages and say so in the trace. Do not label sequential work as parallel execution.

Supporting skills do not replace the mode router. For example, if a Superpowers-style TDD or parallel-agent skill is installed, use it as a method only after this skill selects Lite Orchestration or Full Harness.

## Filesystem And Sandbox

Codex work is usually grounded in the local workspace. The manager should:

- inspect `git status` before edits
- avoid reverting unknown user changes
- keep writes inside the user's authorized file set
- use worktrees only when the repository state and task split justify them
- write durable run state to the project workspace or another user-approved artifact path

Sandbox and approval limits are part of the capability record. Missing permission is a stop or fallback, not a reason to fabricate evidence.

## Tools And Browser Verification

Browser verification is required for meaningful UI acceptance when a browser tool is available and the task touches user-facing web behavior. If it is unavailable, the manager records the limitation and either uses a narrower check or asks for a decision when the gap affects acceptance.

Shell commands, tests, builds, logs, screenshots, API readbacks, and browser interactions can all become acceptance evidence, but only if the trace records what was checked.

## Sub-Agents And Workers

When Codex has a real delegation mechanism, each worker should receive:

- bounded goal
- allowed paths or responsibility surface
- task-local context that does not require hidden chat history
- required report path
- required evidence
- stop conditions
- four-line return contract

When it does not, the manager can still run the same protocol with sequential stages. The state machine should show the fallback so later readers know no parallel isolation occurred.

Do not delegate two workers to edit the same file or shared state in parallel unless the plan names a merge owner and conflict rule.

## Testing, Review, And Completion

Follow project `AGENTS.md` and local testing instructions first.

For code behavior changes, Codex should identify a verification path before implementation. If meaningful automated tests exist or can be added at reasonable cost, prefer test-first evidence. For docs-only, config-only, or no-test-infrastructure work, record the reason and use a smaller substitute check.

For Full Harness implementation risk, use separate review concerns when possible:

- spec compliance: does the implementation match the request and acceptance criteria?
- code quality: is the change maintainable, scoped, idiomatic, and low-risk?

Before final completion, read the current diff or output, inspect the latest evidence, and state any unverified path. A worker report or skill invocation is not acceptance evidence by itself.

## Hooks And Skills

Skills provide workflow instructions and reusable references. They should not be treated as proof that a capability exists. A skill can tell the manager how to run the harness; the capability gate still decides what can actually be done in the current session.

Hooks, if present in the local setup, are useful for recording or enforcing protocol state, but the manager should not depend on unverified hooks for acceptance. Critical acceptance evidence must be visible in durable artifacts.

## Trace Placement

For complex runs, keep trace in the progress ledger or a dedicated trace file under the task artifact directory. Minimum trace entries:

- capability gate result
- state transitions
- worker or sequential-stage report paths
- evaluator result
- acceptance registry status
- budget breaker events

The final response should summarize evidence, not replace the trace.

Codex workers follow the cooperative protocol and keep writes task-local. The API guard is not a same-user security boundary; native sandbox/OS permissions provide isolation. Managers independently provide `--workspace` for git-based binding validation.
