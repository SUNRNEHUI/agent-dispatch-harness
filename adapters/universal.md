# Universal Runtime Adapter

This skill is **model- and product-agnostic**. Same protocol on Codex, Claude, Grok, or others.

## Shared assumptions

The agent can:

1. Read/write project files
2. Run shell commands (tests, linters, scripts)
3. Optionally spawn sub-agents / parallel workers
4. Optionally use browser or MCP tools

If a capability is missing: **narrow scope, sequential stages, or ask** — never invent parallel results.

Runtime detection should prefer an explicit launcher/adaptor identity, then verified active
capabilities. The presence of an installed `codex`, `claude`, or `grok` executable does not
prove that runtime owns the current session.

Portable route names are `fast`, `main`, `planner`, and `critical_reviewer`. Their concrete
models belong to the runtime adapter (`adapters/codex.md`, `adapters/grok.md`). Sealed maps
live in `scripts/harness_schema.py` and are selected with
`model_router.py --runtime codex|grok`. If per-worker model selection is unavailable, record
the requested profile and the fallback; do not claim the requested model was used.

## Continuation Entry Gate

When a replacement runtime opens a project that may contain a Full run, its first action is
`harnessctl.py resume <project-root> --runtime <runtime> --actor-id <unique-session-id>`.
Do not ask the user for an artifact path and do not depend on the previous chat. If another
owner is still active, include a concrete `--takeover-reason`.

Resume is fail-closed: zero or multiple active runs, corrupt state, broken digest chains, or
unrecoverable transactions block ownership transfer. On success, obey the packet's
`required_reads`, reconcile `workspace_drift`, and use its actor ID plus owner epoch for every
later mutation. A checkpoint records explicit next action and a content fingerprint of the
project worktree; it does not serialize hidden reasoning or provider session state.

There is no portable provider quota callback in this protocol. "Automatic" means the
replacement runtime performs discovery/recovery/claim as its first action after launch.

## Mapping common tools

| Need | Codex-ish | Claude-ish | Grok-ish / generic |
|------|-----------|------------|--------------------|
| Sub-agents | native multi-agent / Task | Task / subagents | Task / sequential fallback |
| Worktree | `git worktree` | worktree / isolation | `git worktree` if git repo |
| Project rules | `AGENTS.md` | `CLAUDE.md` / rules | any project instruction files |
| Verify | shell + tests | shell + hooks | shell + tests |

## Protocol stability

Always keep:

- Density decision (Direct / Lite / Full)
- Spec Synthesis when fuzzy or fake-success-prone
- Evidence before done
- Four-line worker return
- Stop conditions

Do **not** require a specific brand of “agent framework” to follow this skill.

## Token tip

Load `SKILL.md` first. Load at most **one** of `references/*` or `adapters/*` per decision point.
Product-specific adapters (`codex.md`, `grok.md`, `claude-code.md`) only when that runtime's quirks block you.
