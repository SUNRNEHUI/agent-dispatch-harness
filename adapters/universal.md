# Universal Runtime Adapter

This skill is **model- and product-agnostic**. Same protocol on Codex, Claude, Grok, or others.

## Shared assumptions

The agent can:

1. Read/write project files  
2. Run shell commands (tests, linters, scripts)  
3. Optionally spawn sub-agents / parallel workers  
4. Optionally use browser or MCP tools  

If a capability is missing: **narrow scope, sequential stages, or ask** — never invent parallel results.

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
Product-specific adapters (`codex.md`, `claude-code.md`) only when that runtime’s quirks block you.
