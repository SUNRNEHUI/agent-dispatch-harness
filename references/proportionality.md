# Proportionality Guide

How much harness to write so models stay precise **without** burning tokens.

## Decision checklist (30 seconds)

1. Can one agent finish and verify in one sitting with low false-completion risk? → **Direct**
2. Is success easy to fake (proxy UI, “tests green”, self-report)? → **Synthesize** (compact minimum)
3. Is the goal fuzzy (更快/更好/专业一点) without a measurable terminal? → **Synthesize**
4. Are there ≥2 independent ownership surfaces **and** user authorized workers? → **Lite**
5. Multi-session, high risk, evaluator, worktree isolation, or durable evidence? → **Full**

If none of 2–5 → Direct. If 2–3 only → synthesize then Direct/Lite. If 5 → Full.

## Density matrix

| Artifact | Direct | Direct+ | Lite | Full |
|----------|--------|---------|------|------|
| Chat plan (≤10 lines) | optional | yes | yes | summary only |
| `synthesis_notes.md` | no | if fuzzy | if fuzzy | optional (prefer task_spec) |
| `task_spec.md` | no | no | rare | yes |
| `acceptance_registry.json` | no | no | rare | yes (+ pass_algorithm) |
| `run_state.json` | no | no | **no** (unless escalated) | yes |
| `tasks/*.md` contracts | no | no | optional short | yes |
| Worker reports | no | no | compact | required |
| `score_harness` | no | no | optional | when judging plan quality |

## When writing costs more than it saves

- Single-file fix with clear test
- Docs-only wording tweak
- User asked a factual question
- You would spend more tokens explaining the DAG than doing the work

Then: **Direct**. Say briefly if user asked for multi-agent on a tiny task.

## When under-writing costs more than tokens

- Performance/correctness with proxy metrics
- Cross-session work
- Parallel agents on shared files without ownership
- User cannot define done; you skip synthesis and “just code”

Then: at least **compact synthesis**; Full if long/resumable.

## Compact synthesis template (copy)

```markdown
## Success
- User sees: …
- System: …

## Not success
1. …
2. …
3. …

## Constraints / non-goals
- …

## Accept
- Rule or TBD after measure: …

## Steps (risk order)
0. …
1. …

## First action / Stop if
- …
```

## Full init (only Full)

```bash
python3 <skill-dir>/scripts/init_run.py \
  --project-root <project> \
  --title "<title>" \
  --with-synthesis
# add --agents a,b only when dispatch is real; they stay planned until synthesis passes
```

## Anti-patterns

| Anti-pattern | Fix |
|--------------|-----|
| Full `workspace/` for typo | Direct |
| Empty `init_run` treated as plan | Fill synthesis; empty = intake only |
| Keyword-stuffed fake plan | Use real pass_algorithm; score_harness integrity |
| Invent SLOs to look precise | TBD + measurement plan |
| Chat dumps of entire JSON state | Paths + 4-line status |
