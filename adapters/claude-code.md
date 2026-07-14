# Claude Code Runtime Adapter

This adapter maps the harness protocol onto Claude Code or similar environments. Prefer `SKILL.md` v5.8+ density rules and `adapters/universal.md` first; this file is Claude-specific control points only.

## Persistent Instructions

Use the most specific instruction source available:

- repository or directory `CLAUDE.md`
- user or project harness instructions
- task artifacts created for the current run
- local hook configuration when it exists and is relevant

The manager should treat instruction files as policy inputs, not as evidence. Acceptance still requires concrete checks.

## Mode Selection Gate

In Claude Code-style harnesses, configured subagents can make dispatch easy enough to overuse. Still run the right-sizing decision first. For small edits, narrow bugs, direct commands, or one-file changes, skip subagents and complete the work directly with normal verification.

Do not default to subagents, background jobs, worktrees, or full artifact initialization merely because the runtime makes them convenient. Medium tasks should normally use Lite Orchestration: a short plan, bounded worker or stage reports when useful, and targeted acceptance evidence. Escalate to Full Harness only for resumable, high-risk, multi-stage, evaluator-sensitive, or rollback-heavy work.

## Capability Gate

Record the actual controls available in the current Claude Code session:

- filesystem write scope
- shell and sandbox behavior
- network assumptions
- available tools
- browser or UI verification route, if any
- subagent support, if configured
- hook support for preflight, post-tool, or notification behavior
- supporting skills or methods for TDD, worktrees, systematic debugging, code review, verification, or parallel-agent discipline
- whether git worktrees are safe for this repository state

If a named control is not present in the active runtime, mark it unavailable and choose a fallback.

Supporting methods are not a competing router. Run Mode Selection first, then borrow TDD, review, worktree, verification, or parallel-agent discipline only when the selected mode justifies it.

## Filesystem, Worktrees, And Ownership

Claude Code-style harnesses often run close to the repository. The manager should:

- read the current repository instructions before modifying files
- inspect git status before creating worktrees or merging outputs
- assign disjoint file or responsibility surfaces to workers
- keep generated artifacts in an agreed task directory
- never overwrite unrelated local changes without user direction

Worktrees are an isolation option, not a default requirement. Use them when parallel edits would otherwise collide or when rollback value is high.

## Tools, Browser, And Evidence

Tool availability varies by harness configuration. The manager should record:

- which command checks were run
- which files or logs were read
- whether browser verification was possible
- whether UI evidence came from screenshots, interaction, console checks, or a declared fallback

If user-facing UI cannot be checked in the active environment, the acceptance registry item should remain `blocked` or require a user decision. It should not become `pass` merely because code was changed.

## Subagents

When subagents are available, each assignment should include:

- exact ownership boundary
- fresh task-local context
- required output path
- evidence required for acceptance
- stop conditions
- instruction to avoid reverting unrelated changes
- four-line return contract

When subagents are not available, run the protocol as sequential stages and record that fallback. The core state machine remains useful even without parallel execution.

Do not dispatch parallel subagents into the same file or shared state unless the plan names a merge owner and conflict rule.

## Testing, Review, And Completion

Follow repository instructions first. For code behavior changes, identify the verification path before implementation. Use test-first evidence when meaningful tests exist or can be added at reasonable cost; otherwise record why and use a smaller substitute check.

For Full Harness implementation risk, separate spec compliance review from code quality review when possible. Review output is evidence for the manager, not final acceptance.

Before final completion, the manager should inspect the current diff or output, read the latest verification evidence, and state any unverified path.

## Hooks

Hooks can help enforce or record the harness:

- preflight checks before risky operations
- post-command trace capture
- report validation
- notification or stop behavior

Hooks are support rails, not the source of truth. The manager still owns state transitions, registry status, and final acceptance.

## Trace Placement

For long or resumable work, keep trace next to the task spec and progress ledger. A minimal Claude Code trace should include:

- instruction files consulted
- capability gate result
- state transitions
- subagent or sequential-stage reports
- evaluator result
- acceptance registry status
- budget breaker events

The final handoff should point to the trace and registry rather than re-explaining every tool call in chat.
